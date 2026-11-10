"""Images: S3-compatible object storage (Garage) or, in development, the local disk.

Objects are flat names (``prod_<ts><rand>.jpg``, ``avatar_...``, ``logo.jpg``);
the database stores their public URL ``MEDIA_BASE_URL/<name>`` (the frontend
proxies ``/media/*`` to the bucket's website endpoint). Requests are signed
with AWS Signature V4 using the standard library only (no boto3: ~80 MB less
in the image and in RAM).
"""

import datetime
import hashlib
import hmac
import http.client
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET  # nosec B405 - parses our own storage's replies

from . import config, logs

NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "svg": "image/svg+xml",
}
# Objects created by the admin (deletable); the rest ships with the code.
UPLOAD_PREFIXES = ("prod_", "avatar_")
log = logs.get("storage")


class StorageError(Exception):
    pass


def _ctype(name):
    return _CONTENT_TYPES.get(name.rsplit(".", 1)[-1].lower(), "application/octet-stream")


# ---------------------------------------------------------------------------
# S3 (SigV4)
# ---------------------------------------------------------------------------


def _sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _s3_request(method, name="", body=b"", query=None, content_type=None):
    endpoint = urllib.parse.urlsplit(config.S3_ENDPOINT)
    host = endpoint.netloc
    path = "/" + config.S3_BUCKET + ("/" + urllib.parse.quote(name) if name else "")
    query_items = sorted((query or {}).items())
    canonical_query = "&".join(
        f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(str(v), safe='-_.~')}"
        for k, v in query_items
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    if content_type:
        headers["content-type"] = content_type
    signed = ";".join(sorted(headers))
    canonical = "\n".join(
        [
            method,
            path,
            canonical_query,
            "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)),
            signed,
            payload_hash,
        ]
    )
    scope = f"{day}/{config.S3_REGION}/s3/aws4_request"
    to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()]
    )
    key = _sign(("AWS4" + config.S3_SECRET_KEY).encode(), day)
    for part in (config.S3_REGION, "s3", "aws4_request"):
        key = _sign(key, part)
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={config.S3_ACCESS_KEY}/{scope}, "
        f"SignedHeaders={signed}, Signature={signature}"
    )
    conn_cls = (
        http.client.HTTPSConnection if endpoint.scheme == "https" else http.client.HTTPConnection
    )
    conn = conn_cls(host, timeout=30)
    try:
        conn.request(
            method, path + ("?" + canonical_query if canonical_query else ""), body, headers
        )
        res = conn.getresponse()
        data = res.read()
    except OSError as exc:
        raise StorageError(f"storage unreachable: {exc}") from exc
    finally:
        conn.close()
    return res.status, data


def _s3_list():
    names, token = [], None
    ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
    while True:
        query = {"list-type": "2", "max-keys": "1000"}
        if token:
            query["continuation-token"] = token
        status, data = _s3_request("GET", query=query)
        if status != 200:
            raise StorageError(f"list failed: HTTP {status}")
        root = ET.fromstring(data)  # noqa: S314  # nosec B314
        names += [el.text for el in root.iter(ns + "Key")]
        token_el = root.find(ns + "NextContinuationToken")
        if root.findtext(ns + "IsTruncated") != "true" or token_el is None:
            return names
        token = token_el.text


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def enabled_s3():
    return bool(config.S3_ENDPOINT)


def url(name):
    """Public URL of an object (what the database stores)."""
    return f"{config.MEDIA_BASE_URL}/{name}"


def name_from_url(value):
    """Object name of one of our media URLs, or None."""
    prefix = config.MEDIA_BASE_URL + "/"
    if not value or not value.startswith(prefix):
        return None
    name = value[len(prefix) :]
    return name if NAME_RE.match(name) else None


def ensure_seed_media():
    """Copy the images shipped with the code into the bucket when missing."""
    folder = config.SEED_MEDIA_DIR
    if not os.path.isdir(folder):
        return 0
    present = set(list_names())
    copied = 0
    for name in sorted(os.listdir(folder)):
        full = os.path.join(folder, name)
        if name in present or not os.path.isfile(full) or not NAME_RE.match(name):
            continue
        with open(full, "rb") as fh:
            put(name, fh.read())
        copied += 1
    if copied:
        log.info("seed images copied to the storage", extra={"count": copied})
    return copied


def put(name, data):
    if not NAME_RE.match(name):
        raise StorageError("invalid object name")
    if enabled_s3():
        status, body = _s3_request("PUT", name, data, content_type=_ctype(name))
        if status not in (200, 201):
            raise StorageError(f"upload failed: HTTP {status} {body[:200]!r}")
        return
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    with open(os.path.join(config.UPLOAD_DIR, name), "wb") as fh:
        fh.write(data)


def get(name):
    if not NAME_RE.match(name):
        return None
    if enabled_s3():
        status, body = _s3_request("GET", name)
        return body if status == 200 else None
    try:
        with open(os.path.join(config.UPLOAD_DIR, name), "rb") as fh:
            return fh.read()
    except OSError:
        return None


def delete(name):
    if not NAME_RE.match(name):
        return
    try:
        if enabled_s3():
            _s3_request("DELETE", name)
        else:
            os.remove(os.path.join(config.UPLOAD_DIR, name))
    except (OSError, StorageError) as exc:
        log.warning("image delete failed", extra={"object": name, "error": str(exc)})


def list_names():
    if enabled_s3():
        return _s3_list()
    if not os.path.isdir(config.UPLOAD_DIR):
        return []
    return sorted(
        n
        for n in os.listdir(config.UPLOAD_DIR)
        if not n.startswith(".") and os.path.isfile(os.path.join(config.UPLOAD_DIR, n))
    )


def content_type(name):
    return _ctype(name)
