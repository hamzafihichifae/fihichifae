"""MySQL persistence: connection pool, schema, seeds, sessions and admin credentials.

One MySQL database holds everything:

- the *live* tables the shop works with (catalog, orders, admin account,
  sessions, newsletter subscribers);
- the ``*_archive`` tables keeping deleted products and categories.

Queries are written with ``?`` placeholders (translated for PyMySQL) and rows
behave like ``sqlite3.Row``: ``row["col"]``, ``row[0]``, ``row.keys()``.
``with live_db() as conn:`` is one transaction: committed on success, rolled
back on error.
"""

import contextlib
import datetime
import io
import queue
import secrets
import threading
import time
import zipfile
import zoneinfo

import pymysql
import pymysql.converters
import pymysql.cursors
from pymysql.constants import FIELD_TYPE

from . import config, logs, storage
from .security import hash_password, hash_token, verify_password

_lock = threading.RLock()
# Public name so other modules can serialize compound write transactions.
db_lock = _lock

_TZ = zoneinfo.ZoneInfo(config.TIMEZONE)
log = logs.get("db")

# ---------------------------------------------------------------------------
# connections
# ---------------------------------------------------------------------------


class Row(dict):
    """dict that also accepts positional access, like sqlite3.Row."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return dict.__getitem__(self, key)


class _Cursor(pymysql.cursors.DictCursor):
    dict_type = Row


# SUM()/AVG() over integers return DECIMAL: keep plain numbers for JSON.
_CONV = pymysql.converters.conversions.copy()
_CONV[FIELD_TYPE.NEWDECIMAL] = float
_CONV[FIELD_TYPE.DECIMAL] = float


def _sql(query):
    """``?`` placeholders -> PyMySQL's ``%s`` (literal ``%`` escaped)."""
    return query.replace("%", "%%").replace("?", "%s")


class Connection:
    """Thin wrapper giving PyMySQL the small API the code base uses."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, query, args=()):
        cur = self.raw.cursor()
        cur.execute(_sql(query), tuple(args))
        return cur

    def executemany(self, query, rows):
        rows = [tuple(r) for r in rows]
        cur = self.raw.cursor()
        if rows:
            cur.executemany(_sql(query), rows)
        return cur

    def escape(self, value):
        return self.raw.escape(value)


def _open():
    return pymysql.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=_Cursor,
        conv=_CONV,
        autocommit=False,
        connect_timeout=10,
        read_timeout=60,
        write_timeout=60,
        init_command="SET SESSION time_zone='+00:00', sql_mode='STRICT_ALL_TABLES,"
        "ONLY_FULL_GROUP_BY,NO_ENGINE_SUBSTITUTION'",
    )


class _Pool:
    """Small LIFO pool: idle connections are reused, extra ones are closed."""

    def __init__(self, size):
        self._idle = queue.LifoQueue(maxsize=size)

    def get(self):
        try:
            raw = self._idle.get_nowait()
        except queue.Empty:
            return _open()
        try:
            raw.ping(False)  # stale (server restarted / idle timeout) -> fresh connection
        except pymysql.MySQLError:
            raw.close()
            return _open()
        return raw

    def put(self, raw):
        try:
            self._idle.put_nowait(raw)
        except queue.Full:
            raw.close()


_pool = _Pool(config.MYSQL_POOL_SIZE)


@contextlib.contextmanager
def live_db():
    """One transaction on the shop database."""
    raw = _pool.get()
    ok = False
    try:
        yield Connection(raw)
        raw.commit()
        ok = True
    finally:
        if ok:
            _pool.put(raw)
        else:
            try:
                raw.rollback()
                _pool.put(raw)
            except pymysql.MySQLError:
                raw.close()


def wait_for_mysql(timeout=None):
    """Retry the first connection while the MySQL service is booting."""
    deadline = time.time() + (config.MYSQL_CONNECT_WAIT if timeout is None else timeout)
    while True:
        try:
            _pool.put(_open())
            return
        except pymysql.MySQLError as exc:
            if time.time() > deadline:
                raise SystemExit(
                    f"[db] cannot reach MySQL at {config.MYSQL_HOST}:{config.MYSQL_PORT} ({exc})"
                ) from exc
            log.info("waiting for mysql", extra={"error": str(exc)})
            time.sleep(2)


# ---------------------------------------------------------------------------
# time helpers (shop local time, Morocco)
# ---------------------------------------------------------------------------


def now():
    """Current shop-local timestamp, ``YYYY-MM-DDTHH:MM:SS``."""
    return datetime.datetime.now(_TZ).strftime("%Y-%m-%dT%H:%M:%S")


def current_month():
    return datetime.datetime.now(_TZ).strftime("%Y-%m")


# ---------------------------------------------------------------------------
# demo catalog (only inserted when FIHI_SEED_DEMO=1, e.g. for local previews)
# ---------------------------------------------------------------------------

SEED_CATEGORIES = [
    ("amlou", "أملو", "Amlou", "Amlou", "prod-amlou.svg"),
    ("miels", "العسل", "Miel", "Honey", "prod-miel.svg"),
    ("huiles", "الزيوت", "Huiles", "Oils", "cat-argan.svg"),
    ("cosmetiques", "عطور", "Parfums", "Perfumes", "cat-promo.svg"),
    ("autres", "منتوجات أخرى", "Autres produits", "Other products", "prod-pack.svg"),
    ("recettes", "وصفات فيه شفاء", "Recettes", "Recipes", "prod-coffret.svg"),
    ("packs", "باقات فيه شفاء", "Packs", "Packs", "prod-pack.svg"),
    ("thes", "الشاي", "Thés", "Teas", "story.svg"),
]

# (id, name, cat, min, max, img, ribbon, featured)
SEED_PRODUCTS = [
    ("s-amlou-01", "أملو بالكاوكاو وزيت الزيتون والعسل", "amlou", 95, None, None, 0, 0),
    ("s-amlou-02", "أملو باللوز وزيت أركان والعسل الحر", "amlou", 109, 239, None, 1, 1),
    ("s-amlou-03", "أملو باللوز وزيت الزيتون والعسل", "amlou", 99, 189, None, 0, 0),
    ("s-miels-01", "عسل السدر", "miels", 350, None, "prod1.jpg", 0, 0),
    ("s-miels-02", "عسل الأكالبتوس الحر", "miels", 350, None, "prod2.jpg", 0, 1),
    ("s-miels-03", "عسل الزعتر الحر", "miels", 350, None, "prod3.jpg", 0, 0),
    ("s-miels-04", "عسل الخروب الحر", "miels", 350, None, "prod4.jpg", 0, 0),
    ("s-miels-05", "عسل الزكوم الحر", "miels", 350, None, "prod5.jpg", 0, 0),
    ("s-huiles-01", "زيت أركان للتجميل", "huiles", 75, None, None, 0, 0),
    ("s-huiles-02", "زيت أركان للأكل", "huiles", 250, None, None, 0, 0),
    ("s-huiles-03", "زيت الزيتون", "huiles", 140, None, None, 0, 0),
    ("s-huiles-04", "زيت الخروع", "huiles", 80, None, None, 0, 0),
    ("s-huiles-05", "زيت اللوز الحلو", "huiles", 25, None, None, 0, 0),
    ("s-huiles-06", "زيت اللوز المر", "huiles", 25, None, None, 0, 0),
    ("s-huiles-07", "زيت الأزير", "huiles", 50, None, None, 0, 0),
    ("s-huiles-08", "زيت السمسم", "huiles", 35, None, None, 0, 0),
    ("s-huiles-09", "زيت القنب الهندي", "huiles", 65, None, None, 0, 0),
    ("s-cosm-01", "صابونة الأركان", "cosmetiques", 50, None, None, 0, 0),
    ("s-cosm-02", "كريم الشيا", "cosmetiques", 50, None, None, 0, 0),
    ("s-cosm-03", "غاسول بالورد", "cosmetiques", 60, None, None, 0, 0),
    ("s-cosm-04", "ماسك الطين الأخضر", "cosmetiques", 35, None, None, 0, 0),
    ("s-cosm-05", "تونر ماء الورد", "cosmetiques", 45, None, None, 0, 0),
    ("s-cosm-06", "سكراب الشفاه بالعسل", "cosmetiques", 28, 35, None, 0, 0),
    ("s-autr-01", "سلو رويال", "autres", 100, 150, None, 0, 0),
    ("s-autr-02", "الجيسينك بودرة", "autres", None, None, None, 0, 0),
    ("s-autr-03", "العكبر الخام", "autres", None, None, None, 0, 0),
    ("s-autr-04", "حبوب اللقاح", "autres", None, None, None, 0, 0),
    ("s-autr-05", "خل التفاح", "autres", 35, None, None, 0, 0),
    ("s-autr-06", "الجيسينغ شرائح", "autres", 140, None, None, 0, 0),
    ("s-autr-07", "العكبر البلدي بودرة", "autres", 70, None, None, 0, 0),
    ("s-autr-08", "ليبطون", "autres", 35, None, None, 0, 0),
    ("s-reci-01", "وجبة الطاقة", "recettes", 220, 749, None, 1, 1),
    ("s-reci-02", "وصفة الجهاز الهضمي", "recettes", 100, 360, None, 0, 0),
    ("s-reci-03", "الوصفة المقوية", "recettes", 99, 580, None, 0, 0),
    ("s-reci-04", "الوصفة الملكية 👑", "recettes", 99, 590, None, 1, 0),
    ("s-pack-01", "باقة رمضان", "packs", 449, 689, None, 1, 1),
    ("s-pack-02", "باقة عيد الأضحى المبارك", "packs", 590, None, None, 0, 0),
    ("s-thes-01", "علي المقام", "thes", None, None, None, 0, 0),
    ("s-thes-02", "كشمير", "thes", None, None, None, 0, 0),
    ("s-thes-03", "جبل علي", "thes", 80, None, None, 0, 0),
    ("s-thes-04", "شاي الحاكم", "thes", 105, None, None, 0, 0),
    ("s-thes-05", "المقام الذهبي", "thes", 105, None, None, 0, 0),
]

CAT_IMG = {c[0]: c[4] for c in SEED_CATEGORIES}  # object names in the bucket

# ---------------------------------------------------------------------------
# schema (versioned: each entry runs once, in order)
# ---------------------------------------------------------------------------

_TABLE_OPTS = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"

_PRODUCT_COLUMNS = """
    name VARCHAR(160) NOT NULL,
    name_fr VARCHAR(160) NULL,
    name_en VARCHAR(160) NULL,
    cat VARCHAR(40) NOT NULL,
    `min` DOUBLE NULL, `max` DOUBLE NULL,
    img VARCHAR(255) NULL,
    ribbon TINYINT NOT NULL DEFAULT 0,
    featured TINYINT NOT NULL DEFAULT 0,
    custom TINYINT NOT NULL DEFAULT 0,
    created CHAR(19) NULL,
    sizes TEXT NULL,
    description TEXT NULL"""

MIGRATIONS = [
    # 1 - initial MySQL schema
    [
        "CREATE TABLE IF NOT EXISTS meta(name VARCHAR(64) PRIMARY KEY, value TEXT)" + _TABLE_OPTS,
        "CREATE TABLE IF NOT EXISTS categories("
        " slug VARCHAR(40) PRIMARY KEY,"
        " seq BIGINT NOT NULL AUTO_INCREMENT UNIQUE,"
        " title_ar VARCHAR(120), title_fr VARCHAR(120), title_en VARCHAR(120),"
        " img VARCHAR(255))" + _TABLE_OPTS,
        "CREATE TABLE IF NOT EXISTS products("
        " id VARCHAR(40) PRIMARY KEY,"
        " seq BIGINT NOT NULL AUTO_INCREMENT UNIQUE," + _PRODUCT_COLUMNS + ","
        " KEY idx_products_cat (cat))" + _TABLE_OPTS,
        "CREATE TABLE IF NOT EXISTS orders("
        " id VARCHAR(40) PRIMARY KEY,"
        " buyer VARCHAR(200), phone VARCHAR(30), address VARCHAR(200), city VARCHAR(200),"
        " location VARCHAR(500),"
        " created CHAR(19) NOT NULL,"
        " status VARCHAR(12) NOT NULL DEFAULT 'pending',"
        " confirmed_at CHAR(19) NULL,"
        " delivery_fee DOUBLE NOT NULL DEFAULT 0,"
        " source VARCHAR(12) NOT NULL DEFAULT 'online',"
        " KEY idx_orders_status (status, confirmed_at),"
        " KEY idx_orders_created (created),"
        " KEY idx_orders_buyer (buyer))" + _TABLE_OPTS,
        "CREATE TABLE IF NOT EXISTS order_items("
        " id BIGINT PRIMARY KEY AUTO_INCREMENT,"
        " order_id VARCHAR(40) NOT NULL,"
        " product_id VARCHAR(40) NULL,"
        " product_name VARCHAR(160),"
        " cat VARCHAR(40),"
        " price DOUBLE, qty INT,"
        " created CHAR(19), size VARCHAR(20),"
        " KEY idx_order_items_order (order_id))" + _TABLE_OPTS,
        "CREATE TABLE IF NOT EXISTS password_resets("
        " id BIGINT PRIMARY KEY AUTO_INCREMENT,"
        " token_hash CHAR(64) NOT NULL,"
        " email VARCHAR(254),"
        " created BIGINT NOT NULL, expires BIGINT NOT NULL,"
        " used TINYINT NOT NULL DEFAULT 0,"
        " KEY idx_resets_token (token_hash))" + _TABLE_OPTS,
        "CREATE TABLE IF NOT EXISTS sessions("
        " token_hash CHAR(64) PRIMARY KEY,"
        " user VARCHAR(64) NOT NULL, ip VARCHAR(64),"
        " created BIGINT NOT NULL, expires BIGINT NOT NULL,"
        " KEY idx_sessions_expires (expires))" + _TABLE_OPTS,
        "CREATE TABLE IF NOT EXISTS newsletter("
        " email VARCHAR(254) PRIMARY KEY, lang VARCHAR(2), created CHAR(19))" + _TABLE_OPTS,
        # deleted products / categories (restorable from the admin)
        "CREATE TABLE IF NOT EXISTS products_archive("
        " id VARCHAR(40) PRIMARY KEY,"
        " original_id VARCHAR(40)," + _PRODUCT_COLUMNS.replace(" NOT NULL,", ",") + ","
        " revoked_at CHAR(19), revoked_by VARCHAR(64),"
        " KEY idx_products_archive_original (original_id))" + _TABLE_OPTS,
        "CREATE TABLE IF NOT EXISTS categories_archive("
        " id VARCHAR(40) PRIMARY KEY,"
        " slug VARCHAR(40),"
        " title_ar VARCHAR(120), title_fr VARCHAR(120), title_en VARCHAR(120),"
        " img VARCHAR(255),"
        " archived_at CHAR(19), archived_by VARCHAR(64),"
        " KEY idx_categories_archive_slug (slug))" + _TABLE_OPTS,
    ],
]

# Tables in dependency-free order (backups, tests).
TABLES = (
    "meta",
    "categories",
    "products",
    "orders",
    "order_items",
    "password_resets",
    "sessions",
    "newsletter",
    "products_archive",
    "categories_archive",
)

# Categories whose display name is brand-consistent and must stay in sync
# with previously-seeded databases.
CATEGORY_NAME_UPDATES = [
    ("recettes", "وصفات فيه شفاء", "Recettes", "Recipes"),
    ("packs", "باقات فيه شفاء", "Packs", "Packs"),
    ("cosmetiques", "عطور", "Parfums", "Perfumes"),
]


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE name=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta(name,value) VALUES(?,?) ON DUPLICATE KEY UPDATE value=VALUES(value)",
        (key, value),
    )


def unique_id(prefix):
    return f"{prefix}{int(time.time() * 1000)}{secrets.token_hex(3)}"


def _migrate(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta(name VARCHAR(64) PRIMARY KEY, value TEXT)" + _TABLE_OPTS
    )
    version = int(get_meta(conn, "schema_version", "0") or 0)
    for number, statements in enumerate(MIGRATIONS, start=1):
        if number <= version:
            continue
        for statement in statements:
            conn.execute(statement)
        set_meta(conn, "schema_version", str(number))
        log.info("schema migrated", extra={"version": number})


def init_db():
    """Create/migrate the schema, seed the admin."""

    wait_for_mysql()
    storage.ensure_seed_media()  # logo, category pictures, demo photos -> bucket
    with _lock:
        with live_db() as conn:
            _migrate(conn)
        with live_db() as conn:
            sync_media_urls(conn)
        with live_db() as conn:
            # demo catalog only on request (a real shop starts empty)
            if config.SEED_DEMO and not get_meta(conn, "seeded"):
                conn.executemany(
                    "INSERT IGNORE INTO categories(slug,title_ar,title_fr,title_en,img)"
                    " VALUES(?,?,?,?,?)",
                    [c[:4] + (storage.url(c[4]),) for c in SEED_CATEGORIES],
                )
                ts = now()
                conn.executemany(
                    "INSERT IGNORE INTO products"
                    " (id,name,cat,`min`,`max`,img,ribbon,featured,custom,created)"
                    " VALUES(?,?,?,?,?,?,?,?,0,?)",
                    [
                        (
                            p[0],
                            p[1],
                            p[2],
                            p[3],
                            p[4],
                            storage.url(p[5] or CAT_IMG[p[2]]),
                            p[6],
                            p[7],
                            ts,
                        )
                        for p in SEED_PRODUCTS
                    ],
                )
                set_meta(conn, "seeded", "1")
                log.info("seeded demo catalog", extra={"products": len(SEED_PRODUCTS)})

            # keep previously-seeded databases in sync with the brand
            for slug, ar, fr, en in CATEGORY_NAME_UPDATES:
                conn.execute(
                    "UPDATE categories SET title_ar=?, title_fr=?, title_en=? WHERE slug=?",
                    (ar, fr, en, slug),
                )
            # orders confirmed before confirmation dates were recorded
            conn.execute(
                "UPDATE orders SET confirmed_at=created"
                " WHERE status='confirmed' AND confirmed_at IS NULL"
            )
            init_admin(conn)
            purge_expired_sessions(conn)


# ---------------------------------------------------------------------------
# image URLs
# ---------------------------------------------------------------------------

IMAGE_COLUMNS = (
    ("categories", "img"),
    ("products", "img"),
    ("products_archive", "img"),
    ("categories_archive", "img"),
)


def sync_media_urls(conn):
    """Make every stored image reference a URL under ``MEDIA_BASE_URL``.

    Rewrites the paths of older releases (``assets/uploads/x.jpg``,
    ``assets/logo.jpg``) and the URLs of a previous base (domain change).
    Idempotent: a no-op once everything uses the current base.
    """
    base = config.MEDIA_BASE_URL + "/"
    previous = get_meta(conn, "media_base_url")
    prefixes = list(config.LEGACY_IMAGE_PREFIXES)
    if previous and previous != base:
        prefixes.insert(0, previous)
    changed = 0
    for table, column in IMAGE_COLUMNS:
        for prefix in prefixes:
            cur = conn.execute(
                f"UPDATE `{table}` SET `{column}` = CONCAT(?, SUBSTRING(`{column}`, ?))"  # noqa: S608
                f" WHERE LEFT(`{column}`, ?) = ?",  # nosec B608 - constant table/column names
                (base, len(prefix) + 1, len(prefix), prefix),
            )
            changed += cur.rowcount
    avatar = get_meta(conn, "admin_avatar") or ""
    for prefix in prefixes:
        if avatar.startswith(prefix):
            set_meta(conn, "admin_avatar", base + avatar[len(prefix) :])
            changed += 1
            break
    set_meta(conn, "media_base_url", base)
    if changed:
        log.info("image references rewritten to media URLs", extra={"rows": changed, "base": base})


# ---------------------------------------------------------------------------
# admin account
# ---------------------------------------------------------------------------


def init_admin(conn):
    """Create the admin account once; upgrade legacy password hashes if any."""
    has_user = get_meta(conn, "admin_user")
    stored_hash = get_meta(conn, "admin_pw_hash")
    if stored_hash and not stored_hash.startswith("pbkdf2$"):
        # legacy (SHA-256) hash from an older build -> re-seed with the
        # configured password using the current, slow hashing scheme.
        _reset_admin_password(conn, "legacy hash upgraded")
    if not has_user:
        if config.IS_PRODUCTION and not config.ADMIN_PASSWORD_FROM_ENV:
            raise SystemExit(
                "[auth] FIHI_ADMIN_PASSWORD must be set to create the admin account in production"
            )
        log.info("admin account created", extra={"user": config.DEFAULT_ADMIN_USER})
        _reset_admin_password(conn, "initial account")
    # initial values only: the admin edits them from the profile panel
    if not get_meta(conn, "admin_email"):
        set_meta(conn, "admin_email", config.DEFAULT_ADMIN_EMAIL)
    if not get_meta(conn, "whatsapp"):
        set_meta(conn, "whatsapp", config.WHATSAPP_NUMBER)


def get_reset_email(conn):
    """Address the reset link goes to (set from the admin profile)."""
    return get_meta(conn, "admin_email", "") or None


def create_reset_record(conn, email):
    """Issue a single-use reset token (30 min TTL) for a password reset."""
    token = secrets.token_hex(32)
    now_ts = int(time.time())
    conn.execute("DELETE FROM password_resets WHERE used=0")  # one pending reset at a time
    conn.execute(
        "INSERT INTO password_resets(token_hash,email,created,expires,used) VALUES(?,?,?,?,0)",
        (hash_token(token), email, now_ts, now_ts + config.RESET_TOKEN_TTL_MS // 1000),
    )
    return token


def consume_reset_token(conn, token):
    """Validate + consume a reset token; returns the account e-mail or None."""
    if not token:
        return None
    row = conn.execute(
        "SELECT id,email,expires FROM password_resets WHERE token_hash=? AND used=0",
        (hash_token(token),),
    ).fetchone()
    if not row:
        return None
    if int(time.time()) > row["expires"]:
        conn.execute("DELETE FROM password_resets WHERE id=?", (row["id"],))
        return None
    conn.execute("UPDATE password_resets SET used=1 WHERE id=?", (row["id"],))
    return row["email"]


def _reset_admin_password(conn, reason):
    pw = config.DEFAULT_ADMIN_PASS
    if len(pw) < config.MIN_PASSWORD_LEN:
        raise SystemExit(
            f"FIHI_ADMIN_PASSWORD must be at least {config.MIN_PASSWORD_LEN} characters"
        )
    salt = secrets.token_hex(8)
    set_meta(conn, "admin_user", config.DEFAULT_ADMIN_USER)
    set_meta(conn, "admin_pw_salt", salt)
    set_meta(conn, "admin_pw_hash", hash_password(pw, salt))
    log.info("admin credentials set", extra={"reason": reason})


def set_admin_password(conn, password):
    """Store a new password (password-reset flow and profile panel)."""
    salt = secrets.token_hex(8)
    set_meta(conn, "admin_pw_salt", salt)
    set_meta(conn, "admin_pw_hash", hash_password(password, salt))


def check_admin_password(conn, password):
    """True when ``password`` is the current admin password (any username)."""
    stored_hash = get_meta(conn, "admin_pw_hash", "")
    salt = get_meta(conn, "admin_pw_salt", "")
    return verify_password(password, salt, stored_hash)


def verify_admin_password(conn, username, password):
    stored_user = get_meta(conn, "admin_user", "")
    # always run the slow hash, so a wrong username takes as long as a wrong password
    ok = check_admin_password(conn, password)
    return ok and username.casefold() == stored_user.casefold()


# ---------------------------------------------------------------------------
# admin sessions (stored hashed, so deployments do not log the admin out)
# ---------------------------------------------------------------------------


def create_session(user, ip):
    token = secrets.token_urlsafe(32)
    now_ts = int(time.time())
    with live_db() as conn:
        purge_expired_sessions(conn)
        conn.execute(
            "INSERT INTO sessions(token_hash,user,ip,created,expires) VALUES(?,?,?,?,?)",
            (hash_token(token), user, ip, now_ts, now_ts + config.SESSION_TTL),
        )
    return token


def get_session(token):
    if not token:
        return None
    with live_db() as conn:
        row = conn.execute(
            "SELECT user,ip,created,expires FROM sessions WHERE token_hash=?",
            (hash_token(token),),
        ).fetchone()
    if not row or row["expires"] <= int(time.time()):
        return None
    return dict(row)


def delete_session(token):
    if not token:
        return
    with live_db() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (hash_token(token),))


def delete_all_sessions(except_token=None):
    with live_db() as conn:
        if except_token:
            conn.execute("DELETE FROM sessions WHERE token_hash<>?", (hash_token(except_token),))
        else:
            conn.execute("DELETE FROM sessions")


def purge_expired_sessions(conn):
    conn.execute("DELETE FROM sessions WHERE expires<=?", (int(time.time()),))


# ---------------------------------------------------------------------------
# backups
# ---------------------------------------------------------------------------


def _sql_dump():
    """Plain SQL dump of every table (schema + rows), restorable with ``mysql``."""
    out = io.StringIO()
    out.write(
        f"-- {config.SITE_NAME} backup {now()}\nSET NAMES utf8mb4;\nSET FOREIGN_KEY_CHECKS=0;\n"
    )
    # one REPEATABLE READ transaction: every SELECT sees the same snapshot
    with live_db() as conn:
        for table in TABLES:
            create = conn.execute(f"SHOW CREATE TABLE `{table}`").fetchone()  # nosec B608
            out.write(f"\nDROP TABLE IF EXISTS `{table}`;\n{create[1]};\n")
            cur = conn.execute(f"SELECT * FROM `{table}`")  # noqa: S608  # nosec B608
            for row in cur:
                cols = ",".join(f"`{c}`" for c in row.keys())
                vals = ",".join(conn.escape(v) for v in row.values())  # driver-escaped literals
                out.write(f"INSERT INTO `{table}` ({cols}) VALUES ({vals});\n")  # noqa: S608
    return out.getvalue()


def backup_zip():
    """Consistent snapshot of the database (SQL dump) + uploaded images, as zip bytes."""
    from . import storage

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("fihi-chifae.sql", _sql_dump())
        for name in storage.list_names():
            data = storage.get(name)
            if data is not None:
                zf.writestr("uploads/" + name, data)
    return buf.getvalue()
