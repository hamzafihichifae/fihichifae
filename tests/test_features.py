"""Admin profile, customer filter, gram sizes, search and object storage."""

import base64
import os

import pytest

from app import account, catalog, orders, search, storage
from app import db as database
from app.catalog import StoreError

# 1x1 transparent PNG
PNG = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
    )
).decode()


# ---------------------------------------------------------------- sizes
def test_gram_sizes_are_accepted_and_priced(category):
    p = catalog.add_product(
        "pytest-grams",
        category["slug"],
        None,
        "",
        sizes=[
            {"size": "250", "unit": "g", "price": 30},
            {"size": "1", "unit": "kg", "price": 100},
        ],
    )
    assert {catalog.size_label(s) for s in p["sizes"]} == {"250g", "1kg"}
    order = orders.create_order(
        {
            "buyer": "pytest grams",
            "phone": "0612345678",
            "address": "rue 1",
            "city": "BHALIL",
            "items": [{"id": p["id"], "size": "250g", "qty": 2}],
        }
    )
    assert order["subtotal"] == 60.0 and order["items"][0]["size"] == "250g"


def test_unknown_unit_is_refused(category):
    with pytest.raises(StoreError) as exc:
        catalog.add_product(
            "pytest-bad-unit",
            category["slug"],
            None,
            "",
            sizes=[{"size": "1", "unit": "lb", "price": 1}],
        )
    assert exc.value.code == "invalid_sizes"


# -------------------------------------------------------------- profile
@pytest.fixture
def known_password(monkeypatch):
    """Give the admin a known password for the test (meta is restored afterwards)."""
    with database.db_lock, database.live_db() as conn:
        database.set_admin_password(conn, "pytest-password-1")
    # never sign the real admin out while testing
    monkeypatch.setattr(database, "delete_all_sessions", lambda except_token=None: None)
    return "pytest-password-1"


def test_profile_change_requires_the_current_password(known_password):
    with pytest.raises(StoreError) as exc:
        account.update_profile({"current_password": "nope", "email": "a@b.co"}, "")
    assert exc.value.status == 403
    with pytest.raises(StoreError) as exc:
        account.update_profile({"email": "a@b.co"}, "")
    assert exc.value.code == "missing_password"


def test_username_password_email_and_phone_change(known_password):
    prof, signed_out = account.update_profile(
        {
            "current_password": known_password,
            "username": "pytest_owner",
            "new_password": "pytest-password-2",
            "email": "Owner@Example.com",
            "phone": "06 12 34 56 78",
        },
        "",
    )
    assert signed_out
    assert prof == {
        "username": "pytest_owner",
        "email": "owner@example.com",
        "phone": "212612345678",
        "avatar": prof["avatar"],
    }
    with database.live_db() as conn:
        assert database.verify_admin_password(conn, "pytest_owner", "pytest-password-2")
        assert not database.verify_admin_password(conn, "pytest_owner", known_password)
        assert database.get_reset_email(conn) == "owner@example.com"
    assert account.shop_phone() == "212612345678"


@pytest.mark.parametrize("value", ["123", "abc", "+1 (234)"])
def test_invalid_phone_is_refused(value):
    with pytest.raises(StoreError):
        account.normalize_phone(value)


@pytest.mark.parametrize("value", ["ab", "has space", "x" * 41])
def test_invalid_username_is_refused(known_password, value):
    with pytest.raises(StoreError) as exc:
        account.update_profile({"current_password": known_password, "username": value}, "")
    assert exc.value.code == "invalid_username"


def test_avatar_is_stored_and_removed():
    # detach the owner's real photo first (meta is restored after the test), so
    # replacing/removing the test photo can never delete it from the storage
    with database.db_lock, database.live_db() as conn:
        database.set_meta(conn, "admin_avatar", "")
    before = set(storage.list_names())
    prof = account.set_avatar("data:image/png;base64," + PNG)
    name = catalog.uploaded_name(prof["avatar"])
    assert name and name.startswith("avatar_") and name in storage.list_names()
    assert storage.get(name).startswith(b"\x89PNG")
    prof = account.remove_avatar()
    assert prof["avatar"] == "" and set(storage.list_names()) == before


def test_avatar_must_be_an_image():
    with pytest.raises(StoreError):
        account.set_avatar("data:text/plain;base64," + base64.b64encode(b"hello").decode())


# ------------------------------------------------------- customer filter
def test_orders_filtered_by_customer_with_all_time_history(product):
    buyer = f"pytest buyer {os.urandom(3).hex()}"

    def place():
        return orders.create_order(
            {
                "buyer": buyer,
                "items": [{"name": product["name"], "cat": product["cat"], "price": 10, "qty": 1}],
            },
            manual=True,
        )["order_id"]

    old, recent = place(), place()
    other = orders.create_order(
        {
            "buyer": "pytest someone else",
            "items": [{"name": "x", "cat": product["cat"], "price": 5, "qty": 1}],
        },
        manual=True,
    )["order_id"]
    with database.live_db() as conn:  # move one of our own orders to an earlier year
        conn.execute(
            "UPDATE orders SET created='2024-03-05T10:00:00', confirmed_at='2024-03-05T10:00:00'"
            " WHERE id=?",
            (old,),
        )
    month = database.current_month()
    this_month = orders.list_orders(month + "-01", month + "-31", buyer.upper())
    assert [o["id"] for o in this_month] == [recent]
    all_time = {o["id"] for o in orders.list_orders(buyer=buyer)}
    assert all_time == {old, recent} and other not in all_time

    summary = orders.customer_summary(buyer)
    assert summary["orders"] == 2 and summary["confirmed"] == 2
    assert summary["first_order"].startswith("2024-03-05")
    assert summary["confirmed_total"] == 20.0

    found = [c for c in orders.list_customers(buyer[:14]) if c["buyer"] == buyer]
    assert found and found[0]["orders"] == 2


def test_customer_search_escapes_like_wildcards():
    # "%" and "_" are literal characters, not wildcards matching every customer
    assert all("%_" in c["buyer"] for c in orders.list_customers("%_"))


# ---------------------------------------------------------------- search
def test_folding_handles_arabic_variants_and_accents():
    assert search.fold("العسل") == ["عسل"]
    assert search.fold("بالعسل والزيت") == ["عسل", "زيت"]
    assert search.fold("أركان") == search.fold("اركان")
    assert search.fold("Thé à la menthe") == ["the", "a", "la", "menthe"]
    assert search.fold("وصفةٌ") == ["وصفه"]


def test_builtin_search_finds_arabic_products_in_three_languages(category):
    unique = "pytestzq" + os.urandom(2).hex()
    p = catalog.add_product(f"عسل {unique}", category["slug"], 10.0, "", name_fr="Miel du désert")
    other = catalog.add_product(f"زيت {unique}", category["slug"], 10.0, "")
    for query in (
        unique,
        f"العسل {unique}",
        f"honey {unique}",
        f"miel {unique}",
        f"désert {unique}",
    ):
        ids = search._local_search(query, 10)
        assert ids and ids[0] == p["id"], query
    assert search._local_search(f"oil {unique}", 10) == [other["id"]]
    assert search._local_search(f"{unique[:-1]}", 10)  # prefix while typing
    assert search._local_search("zzzz-nothing-matches", 10) == []


def test_search_endpoint_logic_limits_and_empty_query():
    assert search.search("   ")["ids"] == []
    assert len(search.search("a" * 500, limit=1000)["ids"]) <= 60


# ---------------------------------------------------------------- storage
def test_storage_put_get_delete_roundtrip():
    name = f"pytest_{os.urandom(4).hex()}.png"
    storage.put(name, b"\x89PNG-test")
    assert storage.get(name) == b"\x89PNG-test" and name in storage.list_names()
    storage.delete(name)
    assert storage.get(name) is None


def test_storage_refuses_unsafe_names():
    with pytest.raises(storage.StorageError):
        storage.put("../escape.png", b"x")
    assert storage.get("../escape.png") is None


# ------------------------------------------------------------ image URLs
def test_every_image_is_a_media_url_in_the_storage(category):
    from app import config

    base = config.MEDIA_BASE_URL + "/"
    assert category["img"] == base + "cat-default.svg"
    names = set(storage.list_names())
    assert {"logo.jpg", "cat-default.svg"} <= names  # shipped images live in the bucket
    p = catalog.add_product("pytest-url", category["slug"], 5.0, "data:image/png;base64," + PNG)
    assert p["img"].startswith(base + "prod_")
    assert catalog.uploaded_name(p["img"]) in storage.list_names()
    # shared images are never deleted with a product's photo
    assert catalog.uploaded_name(base + "logo.jpg") is None


def test_old_paths_and_old_domain_are_rewritten_to_media_urls(category):
    from app import config

    base = config.MEDIA_BASE_URL + "/"
    p = catalog.add_product("pytest-legacy-img", category["slug"], 5.0, "")
    with database.db_lock, database.live_db() as conn:
        for old, expected in (
            ("assets/uploads/prod_1.jpg", base + "prod_1.jpg"),
            ("assets/prod1.jpg", base + "prod1.jpg"),
            ("https://old.example/media/prod_2.jpg", base + "prod_2.jpg"),
        ):
            database.set_meta(conn, "media_base_url", "https://old.example/media/")
            conn.execute("UPDATE products SET img=? WHERE id=?", (old, p["id"]))
            database.sync_media_urls(conn)
            img = conn.execute("SELECT img FROM products WHERE id=?", (p["id"],)).fetchone()[0]
            assert img == expected, old
        database.sync_media_urls(conn)  # idempotent
        assert conn.execute("SELECT img FROM products WHERE id=?", (p["id"],)).fetchone()[0] == (
            base + "prod_2.jpg"
        )
