"""Test fixtures.

RULE FOR EVERY TEST IN THIS SUITE
---------------------------------
Tests are allowed to run against the real (production) MySQL database and
object storage, but each test MUST delete everything it created: rows in the
live and ``*_archive`` tables and uploaded images. Nothing a test adds may stay.

This is enforced automatically, not left to each test:

- ``_cleanup_after_each_test`` (autouse) snapshots the primary keys of every
  table, the ``meta`` values and the stored image names before a test, and
  afterwards deletes every row and object that did not exist before (and puts
  ``meta`` back) - even when the test fails.
- ``_verify_databases_untouched`` (session) compares row counts at the start
  and at the end of the whole run and fails the run if anything was left.

Tests must not *modify* pre-existing rows other than ``meta`` (only rows they
created), because the snapshot removes additions, it does not undo edits.

Connection settings come from the environment, else from ``.env`` (the
docker compose stack exposes MySQL, Garage and Meilisearch on 127.0.0.1).
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_dotenv():
    path = os.path.join(ROOT, ".env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()
os.environ["FIHI_ENV"] = "development"
os.environ.pop("FIHI_SEED_DEMO", None)
os.environ["FIHI_FLUENTD_URL"] = ""

import pytest  # noqa: E402

from app import config, storage  # noqa: E402
from app import db as database  # noqa: E402

PRIMARY_KEYS = {
    "meta": "name",
    "categories": "slug",
    "products": "id",
    "orders": "id",
    "order_items": "id",
    "password_resets": "id",
    "sessions": "token_hash",
    "newsletter": "email",
    "products_archive": "id",
    "categories_archive": "id",
}


def _snapshot():
    keys, meta = {}, {}
    with database.live_db() as conn:
        for table, pk in PRIMARY_KEYS.items():
            keys[table] = {r[0] for r in conn.execute(f"SELECT `{pk}` FROM `{table}`")}
        meta = {r["name"]: r["value"] for r in conn.execute("SELECT name, value FROM meta")}
        # a username change renames the open sessions: put the real ones back too
        users = {
            r["token_hash"]: r["user"]
            for r in conn.execute("SELECT token_hash, user FROM sessions")
        }
    return keys, meta, users, set(storage.list_names())


def _restore(snapshot):
    keys, meta, users, objects = snapshot
    with database.db_lock, database.live_db() as conn:
        for table, pk in PRIMARY_KEYS.items():
            created = [
                r[0]
                for r in conn.execute(f"SELECT `{pk}` FROM `{table}`")
                if r[0] not in keys[table]
            ]
            conn.executemany(
                f"DELETE FROM `{table}` WHERE `{pk}`=?", [(k,) for k in created]  # nosec B608
            )
        for name, value in meta.items():
            database.set_meta(conn, name, value)
        conn.executemany(
            "UPDATE sessions SET user=? WHERE token_hash=?", [(u, t) for t, u in users.items()]
        )
    for name in set(storage.list_names()) - objects:
        storage.delete(name)


def _counts():
    with database.live_db() as conn:
        out = {
            t: conn.execute(f"SELECT COUNT(*) FROM `{t}`").fetchone()[0]  # nosec B608
            for t in PRIMARY_KEYS
        }
    out["objects"] = len(storage.list_names())
    return out


@pytest.fixture(scope="session", autouse=True)
def _verify_databases_untouched():
    database.init_db()  # schema/migrations first, so they are not mistaken for test data
    start = _counts()
    yield
    end = _counts()
    leftovers = {k: (start.get(k, 0), v) for k, v in end.items() if start.get(k, 0) != v}
    if config.MEILI_URL:  # drop test products from the search index too
        from app import search

        try:
            search._meili_setup()
            search._meili_reindex(search._documents())
        except OSError:
            pass
    assert not leftovers, f"tests left data behind (table: before -> after): {leftovers}"


@pytest.fixture(autouse=True)
def _cleanup_after_each_test():
    snapshot = _snapshot()
    try:
        yield
    finally:
        _restore(snapshot)


@pytest.fixture
def category():
    """A throw-away category (removed automatically after the test)."""
    from app import catalog

    return catalog.create_category(f"pytest-cat-{os.urandom(4).hex()}")


@pytest.fixture
def product(category):
    """A throw-away product priced 100 MAD per kg (removed automatically)."""
    from app import catalog

    return catalog.add_product(f"pytest-prod-{os.urandom(4).hex()}", category["slug"], 100.0, "")
