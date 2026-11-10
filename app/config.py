"""Central configuration for the fihi-chifae application.

Production runs as separate services (one container each):

- backend   - this Python API (stateless)
- mysql     - live tables + ``*_archive`` tables (deleted products/categories)
- storage   - Garage, S3-compatible object storage for uploaded images
- search    - Meilisearch, product search in Arabic / French / English
- fluentd   - log collector (local docker compose only)
- frontend  - nginx: static pages, /api proxy, images from the storage

Everything is configured through environment variables (see .env.example).
Without ``FIHI_S3_ENDPOINT`` images are kept on the local disk and without
``FIHI_MEILI_URL`` search runs in-process, so a laptop only needs MySQL.
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENV = os.environ.get("FIHI_ENV", "development").strip().lower()
IS_PRODUCTION = ENV == "production"

# ---------------------------------------------------------------------------
# MySQL (live tables and *_archive tables live in the same database)
# ---------------------------------------------------------------------------
MYSQL_HOST = os.environ.get("FIHI_MYSQL_HOST", os.environ.get("MYSQLHOST", "127.0.0.1"))
MYSQL_PORT = int(os.environ.get("FIHI_MYSQL_PORT", os.environ.get("MYSQLPORT", "3306")) or 3306)
MYSQL_USER = os.environ.get("FIHI_MYSQL_USER", os.environ.get("MYSQLUSER", "fihi"))
MYSQL_PASSWORD = os.environ.get("FIHI_MYSQL_PASSWORD", os.environ.get("MYSQLPASSWORD", ""))
MYSQL_DATABASE = os.environ.get("FIHI_MYSQL_DATABASE", os.environ.get("MYSQLDATABASE", "fihi"))
# Connections kept open for reuse (the server is threaded; MySQL is tuned for 40).
MYSQL_POOL_SIZE = int(os.environ.get("FIHI_MYSQL_POOL_SIZE", "8") or 8)
# Seconds to keep retrying the first connection (MySQL may still be booting).
MYSQL_CONNECT_WAIT = int(os.environ.get("FIHI_MYSQL_CONNECT_WAIT", "90") or 90)

# ---------------------------------------------------------------------------
# Old image paths (assets/...) that may still be stored; rewritten to media
# URLs at start-up.
# ---------------------------------------------------------------------------
LEGACY_IMAGE_PREFIXES = ("/assets/uploads/", "assets/uploads/", "/assets/", "assets/")

# ---------------------------------------------------------------------------
# Images: every image (product photos, category pictures, the admin's photo,
# the logo) is an object in the S3-compatible storage (Garage); the database
# stores its public URL: MEDIA_BASE_URL/<object name>.
# ---------------------------------------------------------------------------
S3_ENDPOINT = os.environ.get("FIHI_S3_ENDPOINT", "").rstrip("/")  # e.g. http://storage:3900
S3_REGION = os.environ.get("FIHI_S3_REGION", "garage")
S3_BUCKET = os.environ.get("FIHI_S3_BUCKET", "uploads")
S3_ACCESS_KEY = os.environ.get("FIHI_S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("FIHI_S3_SECRET_KEY", "")
# Local fallback (development without an object storage)
UPLOAD_DIR = os.environ.get("FIHI_UPLOAD_DIR", os.path.join(BASE, ".media"))
# Images shipped with the code (logo, category pictures, demo catalog): copied
# into the bucket at start-up when missing. Nothing is served from the code.
SEED_MEDIA_DIR = os.path.join(BASE, "seed", "media")

# ---------------------------------------------------------------------------
# Search (Meilisearch). Empty URL -> built-in in-process search.
# ---------------------------------------------------------------------------
MEILI_URL = os.environ.get("FIHI_MEILI_URL", "").rstrip("/")  # e.g. http://search:7700
MEILI_KEY = os.environ.get("FIHI_MEILI_KEY", "")
MEILI_INDEX = os.environ.get("FIHI_MEILI_INDEX", "products")
SEARCH_MAX_PER_WINDOW = int(os.environ.get("FIHI_SEARCH_RATE_LIMIT", "120") or 120)
SEARCH_WINDOW = 60

# ---------------------------------------------------------------------------
# Logs: JSON lines on stdout, also shipped to Fluentd (in_http) when set.
# ---------------------------------------------------------------------------
FLUENTD_URL = os.environ.get("FIHI_FLUENTD_URL", "").rstrip("/")  # e.g. http://fluentd:9880
FLUENTD_TAG = os.environ.get("FIHI_FLUENTD_TAG", "fihi.backend")
LOG_LEVEL = os.environ.get("FIHI_LOG_LEVEL", "INFO").upper()

SITE_NAME = "fihi-chifae"
# Insert the demo catalog into an empty database (local previews only).
SEED_DEMO = os.environ.get("FIHI_SEED_DEMO", "0") == "1"
TIMEZONE = os.environ.get("FIHI_TIMEZONE", "Africa/Casablanca")

# ---------------------------------------------------------------------------
# Admin credentials (used once, to create the account on a fresh database)
# ---------------------------------------------------------------------------
_DEFAULT_PASS = "admin2026"  # noqa: S105  # nosec B105 - dev only, refused in production
DEFAULT_ADMIN_USER = os.environ.get("FIHI_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASS = os.environ.get("FIHI_ADMIN_PASSWORD", _DEFAULT_PASS)
ADMIN_PASSWORD_FROM_ENV = "FIHI_ADMIN_PASSWORD" in os.environ
# Initial address of the password-reset link; the admin changes it from the
# profile panel afterwards (the stored value then wins).
DEFAULT_ADMIN_EMAIL = os.environ.get("FIHI_ADMIN_EMAIL", "hamza.fihichifae@gmail.com").strip()
# Placeholder stored by earlier releases: replaced by DEFAULT_ADMIN_EMAIL at start.
PLACEHOLDER_ADMIN_EMAILS = ("admin@fihi-chifae.com",)

# ---------------------------------------------------------------------------
# E-mail delivery (password-reset link). First match wins:
#   1. Resend HTTPS API (FIHI_RESEND_API_KEY): works on every Railway plan
#      (Railway blocks outbound SMTP below the Pro plan);
#   2. SMTP (FIHI_SMTP_HOST + FIHI_EMAIL_FROM);
#   3. nothing set -> the reset link is written to the server logs.
# ---------------------------------------------------------------------------
RESEND_API_KEY = os.environ.get("FIHI_RESEND_API_KEY", "").strip()
SMTP_HOST = os.environ.get("FIHI_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("FIHI_SMTP_PORT", "587") or 587)
SMTP_USER = os.environ.get("FIHI_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("FIHI_SMTP_PASSWORD", "")
SMTP_USE_TLS = os.environ.get("FIHI_SMTP_USE_TLS", "1") == "1"
EMAIL_FROM = os.environ.get("FIHI_EMAIL_FROM", "")


def _public_base_url():
    explicit = os.environ.get("FIHI_PUBLIC_BASE_URL", "").strip()
    if explicit:
        return explicit
    railway = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if railway:
        return "https://" + railway
    return ""


# Public base used to build the reset link. Never derived from the request's
# Host header in production (prevents reset-link poisoning).
PUBLIC_BASE_URL = _public_base_url()

# Public URL of the images (the frontend proxies /media/* to the bucket). Set
# FIHI_MEDIA_BASE_URL to serve them from elsewhere (e.g. a CDN). When it
# changes, the URLs stored in the database are rewritten at the next start.
MEDIA_BASE_URL = (
    os.environ.get("FIHI_MEDIA_BASE_URL", "").strip() or (PUBLIC_BASE_URL.rstrip("/") + "/media")
).rstrip("/")

# Password-reset token lifetime (single use).
RESET_TOKEN_TTL_MS = int(os.environ.get("FIHI_RESET_TOKEN_TTL_MIN", "30") or "30") * 60 * 1000

# ---------------------------------------------------------------------------
# Security / limits
# ---------------------------------------------------------------------------
SESSION_TTL = 8 * 3600  # admin session lifetime (seconds)
SESSION_COOKIE = "fc_session"
PASSWORD_ITERATIONS = 210_000  # PBKDF2 work factor
MIN_PASSWORD_LEN = 8

# Behind a reverse proxy (Railway, Fly, Render) the client IP comes from
# X-Forwarded-For; only trust it when told so.
TRUST_PROXY = os.environ.get("FIHI_TRUST_PROXY", "1" if IS_PRODUCTION else "0") == "1"

LOGIN_MAX_ATTEMPTS = 5  # failed logins allowed per window
LOGIN_WINDOW = 15 * 60  # rate-limit window (seconds)
# Public orders / newsletter sign-ups allowed per client IP per window.
# Overridable only so load tests (all users share one IP) are not throttled.
ORDER_MAX_PER_WINDOW = int(os.environ.get("FIHI_ORDER_RATE_LIMIT", "10") or 10)
ORDER_WINDOW = 10 * 60
NEWSLETTER_MAX_PER_WINDOW = int(os.environ.get("FIHI_NEWSLETTER_RATE_LIMIT", "5") or 5)
NEWSLETTER_WINDOW = 60 * 60

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # max image payload size
MAX_AVATAR_BYTES = 2 * 1024 * 1024  # admin profile photo
MAX_JSON_BODY = 16 * 1024 * 1024  # product adds carry a base64 image
MAX_SMALL_BODY = 64 * 1024  # login / orders / categories

MAX_NAME_LEN = 80
MAX_CATEGORY_NAME_LEN = 60
MAX_DESCRIPTION_LEN = 2000
MAX_FIELD_LEN = 200  # buyer name, address, city, location link
MAX_ORDER_ITEMS = 50
MAX_ITEM_QTY = 999

MAX_SIZES = 12  # max size variants per product
SIZE_UNITS = ("g", "kg", "L")  # allowed measurement units
# Categories measured in litres by default (oils); everything else defaults to kg.
LIQUID_CATEGORIES = ("huiles",)

# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------
DELIVERY_FEE = 40.0  # MAD
FREE_DELIVERY_THRESHOLD = 500.0  # MAD, items subtotal
# Delivery is always free in the shop's own city.
FREE_DELIVERY_CITY_LATIN = "BHALIL"
FREE_DELIVERY_CITY_AR = "البهاليل"

# WhatsApp number receiving the orders (international format, digits only).
# Initial value only: the admin changes it from the profile panel.
WHATSAPP_NUMBER = os.environ.get("FIHI_WHATSAPP_NUMBER", "212681771457")
