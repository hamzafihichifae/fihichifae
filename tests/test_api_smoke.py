"""HTTP-level checks against a real server process.

The server writes to the same databases; whatever it creates during a test
(sessions, orders, ...) is deleted afterwards by the conftest.py fixtures.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from app import db as database

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def base():
    port = _free_port()
    env = dict(os.environ, FIHI_ENV="development")
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                with urllib.request.urlopen(url + "/api/v1/ping", timeout=1):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("server did not start")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _req(url, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with _opener.open(req, timeout=5) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


@pytest.fixture
def admin_cookie():
    token = database.create_session("pytest", "127.0.0.1")  # deleted by the cleanup fixture
    return {"Cookie": f"fc_session={token}"}


def test_ping_and_catalog(base):
    status, _, body = _req(base + "/api/v1/ping")
    assert status == 200 and json.loads(body)["status"] == "ok"
    status, _, body = _req(base + "/api/v1/catalog")
    data = json.loads(body)
    assert status == 200 and "categories" in data and data["settings"]["whatsapp"]


@pytest.mark.parametrize(
    "path",
    [
        "/fihi-chifae.db",
        "/fihi-chifae-archive.db",
        "/.git/config",
        "/server.py",
        "/app/config.py",
        "/.env.example",
        "/assets/../server.py",
        "/tests/conftest.py",
    ],
)
def test_private_files_are_not_served(base, path):
    status, _, _ = _req(base + path)
    assert status == 404


def test_public_pages_are_served(base):
    for path in ("/", "/index.html", "/info.html", "/admin-login.html", "/assets/style.css"):
        status, headers, _ = _req(base + path)
        assert status == 200, path
        assert "Content-Security-Policy" in headers


def test_admin_pages_require_login(base, admin_cookie):
    for path in ("/admin.html", "/admin-add.html"):
        status, headers, _ = _req(base + path)
        assert status == 302 and headers["Location"].startswith("/admin-login.html")
        status, _, _ = _req(base + path, headers=admin_cookie)
        assert status == 200
    status, _, _ = _req(base + "/assets/admin.js")
    assert status == 401


def test_admin_api_requires_login(base, admin_cookie):
    status, _, _ = _req(base + "/api/v1/sales/summary")
    assert status == 401
    status, _, body = _req(base + "/api/v1/sales/summary", headers=admin_cookie)
    assert status == 200 and "pending" in json.loads(body)


def test_cross_site_writes_are_refused(base, admin_cookie):
    headers = dict(admin_cookie, Origin="https://evil.example")
    status, _, _ = _req(base + "/api/v1/categories", "POST", {"name": "x"}, headers)
    assert status == 403


def test_wrong_password_is_refused(base):
    status, _, body = _req(
        base + "/api/v1/admin/session",
        "POST",
        {"username": "pytest-nobody", "password": "wrong-password"},
    )
    assert status == 401 and json.loads(body)["error"]["code"] == "invalid_credentials"


def test_logout_clears_the_session(base, admin_cookie):
    status, headers, _ = _req(base + "/api/v1/admin/session", "DELETE", headers=admin_cookie)
    assert status == 200 and "Max-Age=0" in headers.get("Set-Cookie", "")
    status, _, _ = _req(base + "/api/v1/admin/session", headers=admin_cookie)
    assert status == 401


def test_public_order_roundtrip(base, admin_cookie, product):
    order = {
        "buyer": "pytest http",
        "phone": "0612345678",
        "address": "rue 2",
        "city": "bhalil",
        "items": [{"id": product["id"], "size": "1kg", "qty": 1, "price": 0.5}],
    }
    status, _, body = _req(base + "/api/v1/orders", "POST", order)
    data = json.loads(body)
    assert status == 201
    assert data["total"] == 100.0 and data["delivery_fee"] == 0 and data["city"] == "BHALIL"
    # the storefront sends the order to the admin's current WhatsApp number
    assert data["whatsapp"].isdigit() and len(data["whatsapp"]) >= 9

    status, _, body = _req(base + "/api/v1/orders", headers=admin_cookie)
    listed = {o["id"]: o for o in json.loads(body)["orders"]}
    assert listed[data["order_id"]]["status"] == "pending"


def test_backup_requires_login_and_contains_the_sql_dump(base, admin_cookie):
    import io
    import zipfile

    status, _, _ = _req(base + "/api/v1/admin/backup")
    assert status == 401
    status, headers, body = _req(base + "/api/v1/admin/backup", headers=admin_cookie)
    assert status == 200 and headers["Content-Type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(body)).namelist()
    assert "fihi-chifae.sql" in names
    dump = zipfile.ZipFile(io.BytesIO(body)).read("fihi-chifae.sql").decode()
    assert "CREATE TABLE `products_archive`" in dump and "CREATE TABLE `orders`" in dump


def test_catalog_cache_is_refreshed_by_admin_changes(base, admin_cookie):
    status, headers, body = _req(base + "/api/v1/catalog")
    etag = headers["ETag"]
    status, _, _ = _req(base + "/api/v1/catalog", headers={"If-None-Match": etag})
    assert status == 304  # unchanged catalog: no body re-sent

    status, _, body = _req(
        base + "/api/v1/categories", "POST", {"name": "pytest-cache-cat"}, admin_cookie
    )
    slug = json.loads(body)["category"]["slug"]
    status, _, body = _req(
        base + "/api/v1/products",
        "POST",
        {"name": "pytest-cache-prod", "cat": slug, "price": 12},
        admin_cookie,
    )
    assert status == 201
    status, headers, body = _req(base + "/api/v1/catalog", headers={"If-None-Match": etag})
    assert status == 200 and headers["ETag"] != etag  # change visible immediately
    names = [p["name"] for c in json.loads(body)["categories"] for p in c["products"]]
    assert "pytest-cache-prod" in names


def test_public_settings_and_search(base, admin_cookie):
    status, _, body = _req(base + "/api/v1/settings")
    assert status == 200 and json.loads(body)["whatsapp"].isdigit()
    status, _, body = _req(
        base + "/api/v1/categories", "POST", {"name": "pytest-search-cat"}, admin_cookie
    )
    slug = json.loads(body)["category"]["slug"]
    status, _, body = _req(
        base + "/api/v1/products",
        "POST",
        {"name": "pytest زيت", "name_fr": "Pytestxq huile", "cat": slug, "price": 10},
        admin_cookie,
    )
    pid = json.loads(body)["id"]
    status, _, body = _req(base + "/api/v1/search?q=pytestxq")
    data = json.loads(body)
    assert status == 200 and data["engine"] in ("meilisearch", "builtin")
    deadline = time.time() + 10  # Meilisearch indexes asynchronously
    while pid not in data["ids"] and time.time() < deadline:
        time.sleep(0.5)
        data = json.loads(_req(base + "/api/v1/search?q=pytestxq")[2])
    assert pid in data["ids"]


def test_profile_and_customers_require_login(base, admin_cookie):
    for method, path in (
        ("GET", "/api/v1/admin/profile"),
        ("PUT", "/api/v1/admin/profile"),
        ("POST", "/api/v1/admin/profile/avatar"),
        ("GET", "/api/v1/orders/customers"),
    ):
        status, _, _ = _req(base + path, method, {} if method != "GET" else None)
        assert status == 401, path
    status, _, body = _req(base + "/api/v1/admin/profile", headers=admin_cookie)
    assert status == 200 and {"username", "email", "phone", "avatar"} <= set(
        json.loads(body)["profile"]
    )
    status, _, body = _req(
        base + "/api/v1/admin/profile",
        "PUT",
        {"current_password": "definitely-wrong", "email": "x@example.com"},
        admin_cookie,
    )
    assert status == 403 and json.loads(body)["error"]["code"] == "wrong_password"
