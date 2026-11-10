"""Orders: validation, server-side pricing, delivery fee, confirmation workflow.

Lifecycle
---------
- Orders placed on the storefront start ``pending``: the seller still has to
  check with the customer (WhatsApp) that the purchase is real.
- ``confirm`` marks the order ``confirmed`` and stamps ``confirmed_at``; only
  confirmed orders count in revenue, reports and best sellers, in the month
  they were confirmed.
- ``reject`` deletes the order permanently.
- Orders entered manually by the admin are confirmed immediately.
"""

import re
import unicodedata

from . import catalog, config
from . import db as database
from .catalog import StoreError

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LATIN_BHALIL = {"bhalil", "bahlil", "bhalile", "bhallil"}
_ARABIC_BHALIL = {"البهاليل", "بهاليل", "البهليل", "بهليل"}


# ---------------------------------------------------------------------------
# delivery
# ---------------------------------------------------------------------------


def _fold(text):
    text = unicodedata.normalize("NFKC", text or "").strip()
    return re.sub(r"[\s\-_.']+", "", text).casefold()


def normalize_city(city):
    """Trim the city; the shop's own city is always written BHALIL / البهاليل."""
    city = re.sub(r"\s+", " ", (city or "")).strip()
    folded = _fold(city)
    if folded in _LATIN_BHALIL:
        return config.FREE_DELIVERY_CITY_LATIN
    if folded in {_fold(c) for c in _ARABIC_BHALIL}:
        return config.FREE_DELIVERY_CITY_AR
    return city


def is_free_delivery_city(city):
    return normalize_city(city) in (config.FREE_DELIVERY_CITY_LATIN, config.FREE_DELIVERY_CITY_AR)


def delivery_fee(subtotal, city):
    """40 MAD unless the order reaches 500 MAD or ships within BHALIL.

    An empty city (in-shop sale entered by the admin) has no delivery.
    """
    city = (city or "").strip()
    if not city or is_free_delivery_city(city):
        return 0.0
    if subtotal >= config.FREE_DELIVERY_THRESHOLD:
        return 0.0
    return config.DELIVERY_FEE


# ---------------------------------------------------------------------------
# validation helpers
# ---------------------------------------------------------------------------


def _text(payload, key, required=False, label="", max_len=config.MAX_FIELD_LEN):
    value = re.sub(r"\s+", " ", str(payload.get(key, "") or "")).strip()
    if required and not value:
        raise StoreError(400, f"missing_{key}", f"{label} مطلوب")
    if len(value) > max_len:
        raise StoreError(400, f"invalid_{key}", f"{label} طويل جداً")
    return value


def _location(payload):
    loc = _text(payload, "location", label="رابط الموقع", max_len=500)
    if loc and not re.match(r"^https?://", loc, re.I):
        raise StoreError(400, "invalid_location", "رابط الموقع يجب أن يبدأ بـ https://")
    return loc


def _qty(item):
    try:
        qty = int(item.get("qty", 0))
    except (TypeError, ValueError):
        raise StoreError(400, "invalid_item", "الكمية غير صالحة") from None
    if not (1 <= qty <= config.MAX_ITEM_QTY):
        raise StoreError(400, "invalid_item", "الكمية غير صالحة")
    return qty


def _items_list(payload):
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise StoreError(400, "empty_cart", "السلة فارغة")
    if len(items) > config.MAX_ORDER_ITEMS:
        raise StoreError(400, "too_many_items", "عدد المنتجات في الطلب كبير جداً")
    if not all(isinstance(it, dict) for it in items):
        raise StoreError(400, "invalid_item", "بيانات المنتج غير صالحة")
    return items


def _find_product(conn, item):
    pid = str(item.get("id", "") or "").strip()
    if pid:
        row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if row:
            return row
    name = str(item.get("name", "") or "").strip()
    cat = str(item.get("cat", "") or "").strip()
    if not name:
        return None
    if cat:
        row = conn.execute(
            "SELECT * FROM products WHERE name=? AND cat=? LIMIT 1", (name, cat)
        ).fetchone()
        if row:
            return row
    return conn.execute("SELECT * FROM products WHERE name=? LIMIT 1", (name,)).fetchone()


def price_public_items(conn, items):
    """Resolve storefront cart lines against the catalog.

    Prices always come from the database; whatever the browser sent is ignored.
    """
    out = []
    for item in items:
        row = _find_product(conn, item)
        if not row:
            raise StoreError(
                400,
                "product_unavailable",
                "أحد المنتجات لم يعد متوفراً، يرجى تحديث السلة",
                name=str(item.get("name", ""))[:80],
            )
        sizes = catalog.product_sizes(row)
        wanted = str(item.get("size", "") or "").strip()
        if sizes:
            match = next((s for s in sizes if catalog.size_label(s) == wanted), None)
            if not match:
                raise StoreError(
                    400,
                    "invalid_size",
                    "الحجم المختار غير متوفر، يرجى تحديث السلة",
                    name=row["name"],
                )
            price, size = float(match["price"]), catalog.size_label(match)
        else:
            # "price on request": recorded at 0, the seller agrees the price on WhatsApp
            price, size = float(row["min"] or 0), ""
        out.append(
            {
                "product_id": row["id"],
                "name": row["name"],
                "cat": row["cat"],
                "price": round(price, 2),
                "qty": _qty(item),
                "size": size,
            }
        )
    return out


def manual_items(conn, items):
    """Admin-entered lines: the seller sets the price (in-shop sales may differ)."""
    out = []
    for item in items:
        name = str(item.get("name", "") or "").strip()
        if not name or len(name) > config.MAX_NAME_LEN:
            raise StoreError(400, "invalid_item", "اسم المنتج مطلوب")
        try:
            price = round(float(item.get("price")), 2)
        except (TypeError, ValueError):
            raise StoreError(400, "invalid_item", "سعر المنتج غير صالح") from None
        if not (0 <= price <= 1_000_000):
            raise StoreError(400, "invalid_item", "سعر المنتج غير صالح")
        cat = str(item.get("cat", "") or "").strip()
        if not catalog.category_exists(conn, cat):
            raise StoreError(400, "invalid_category", "يرجى اختيار فئة المنتج")
        row = _find_product(conn, {"id": item.get("id"), "name": name, "cat": cat})
        out.append(
            {
                "product_id": row["id"] if row and row["cat"] == cat else None,
                "name": name,
                "cat": cat,
                "price": price,
                "qty": _qty(item),
                "size": str(item.get("size", "") or "").strip()[:20],
            }
        )
    return out


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def _subtotal(lines):
    return round(sum(it["price"] * it["qty"] for it in lines), 2)


def create_order(payload, manual=False, source=None):
    """Validate, price and persist an order; returns its public summary."""
    buyer = _text(payload, "buyer", required=True, label="الاسم")
    phone = _text(payload, "phone", required=not manual, label="رقم الهاتف", max_len=30)
    if phone and len(re.sub(r"\D", "", phone)) < 8:
        raise StoreError(400, "invalid_phone", "رقم الهاتف غير صالح")
    address = _text(payload, "address", required=not manual, label="العنوان")
    city = normalize_city(_text(payload, "city", required=not manual, label="المدينة"))
    location = _location(payload)
    items = _items_list(payload)

    oid = database.unique_id("o")
    ts = database.now()
    with database.db_lock, database.live_db() as conn:
        lines = manual_items(conn, items) if manual else price_public_items(conn, items)
        subtotal = _subtotal(lines)
        fee = delivery_fee(subtotal, city)
        status = "confirmed" if manual else "pending"
        conn.execute(
            "INSERT INTO orders(id,buyer,phone,address,city,location,created,status,"
            "confirmed_at,delivery_fee,source) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                oid,
                buyer,
                phone,
                address,
                city,
                location,
                ts,
                status,
                ts if manual else None,
                fee,
                source or ("manual" if manual else "online"),
            ),
        )
        conn.executemany(
            "INSERT INTO order_items(order_id,product_id,product_name,cat,price,qty,created,size)"
            " VALUES(?,?,?,?,?,?,?,?)",
            [
                (
                    oid,
                    it["product_id"],
                    it["name"],
                    it["cat"],
                    it["price"],
                    it["qty"],
                    ts,
                    it["size"],
                )
                for it in lines
            ],
        )
    if manual:  # confirmed sales can change the best sellers
        catalog.bump_catalog_version()
    return {
        "ok": True,
        "order_id": oid,
        "status": status,
        "city": city,
        "items": [{k: it[k] for k in ("name", "size", "price", "qty")} for it in lines],
        "subtotal": subtotal,
        "delivery_fee": fee,
        "total": round(subtotal + fee, 2),
    }


def confirm_order(oid):
    with database.db_lock, database.live_db() as conn:
        row = conn.execute("SELECT status FROM orders WHERE id=?", (oid,)).fetchone()
        if not row:
            raise StoreError(404, "not_found", "الطلب غير موجود")
        if row["status"] != "confirmed":
            conn.execute(
                "UPDATE orders SET status='confirmed', confirmed_at=? WHERE id=?",
                (database.now(), oid),
            )
    catalog.bump_catalog_version()  # best sellers may change
    return {"ok": True, "order_id": oid, "status": "confirmed"}


def reject_order(oid):
    """Rejected orders are deleted permanently (never archived)."""
    with database.db_lock, database.live_db() as conn:
        row = conn.execute("SELECT status FROM orders WHERE id=?", (oid,)).fetchone()
        if not row:
            raise StoreError(404, "not_found", "الطلب غير موجود")
        if row["status"] == "confirmed":
            raise StoreError(409, "already_confirmed", "لا يمكن رفض طلب مؤكد")
        conn.execute("DELETE FROM order_items WHERE order_id=?", (oid,))
        conn.execute("DELETE FROM orders WHERE id=?", (oid,))
    return {"ok": True, "order_id": oid, "status": "rejected"}


# ---------------------------------------------------------------------------
# queries
# ---------------------------------------------------------------------------


def _clean_buyer(buyer):
    return re.sub(r"\s+", " ", buyer or "").strip()[: config.MAX_FIELD_LEN]


def list_orders(date_from=None, date_to=None, buyer=None):
    """Orders (with their lines) whose relevant date falls in [from, to].

    Pending orders are matched on the date they were placed, confirmed orders
    on the date they were confirmed - the same date that drives revenue.
    ``buyer`` keeps only that customer's orders (case-insensitive name).
    """
    for d in (date_from, date_to):
        if d and not _DATE_RE.match(d):
            raise StoreError(400, "invalid_date", "تاريخ غير صالح (YYYY-MM-DD)")
    ref = "CASE WHEN o.status='confirmed' THEN o.confirmed_at ELSE o.created END"
    where, args = [], []
    if date_from:
        where.append(f"substr({ref},1,10) >= ?")
        args.append(date_from)
    if date_to:
        where.append(f"substr({ref},1,10) <= ?")
        args.append(date_to)
    buyer = _clean_buyer(buyer)
    if buyer:
        where.append("o.buyer = ?")
        args.append(buyer)
    # only constant SQL fragments are concatenated; values are bound parameters
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    sql = f"SELECT o.*, {ref} AS ref_date FROM orders o{where_sql}"  # noqa: S608  # nosec B608
    sql += " ORDER BY (o.status='pending') DESC, ref_date DESC"
    with database.live_db() as conn:
        orders = [dict(r) for r in conn.execute(sql, args)]
        lines = {}
        ids = [o["id"] for o in orders]
        for start in range(0, len(ids), 500):  # one query per 500 orders, not one per order
            chunk = ids[start : start + 500]
            marks = ",".join("?" * len(chunk))
            for r in conn.execute(
                "SELECT order_id,product_id,product_name,cat,price,qty,size FROM order_items"  # noqa: S608
                f" WHERE order_id IN ({marks}) ORDER BY id",  # noqa: S608  # nosec B608
                chunk,
            ):
                item = dict(r)
                lines.setdefault(item.pop("order_id"), []).append(item)
    for o in orders:
        o["items"] = lines.get(o["id"], [])
        o["subtotal"] = _subtotal(
            [{"price": i["price"] or 0, "qty": i["qty"] or 0} for i in o["items"]]
        )
        o["delivery_fee"] = o["delivery_fee"] or 0
        o["total"] = round(o["subtotal"] + o["delivery_fee"], 2)
    return orders


def customer_summary(buyer):
    """All-time figures of one customer: order count, first/last order, totals."""
    buyer = _clean_buyer(buyer)
    if not buyer:
        raise StoreError(400, "missing_buyer", "اسم الزبون مطلوب")
    with database.live_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS orders, SUM(o.status='confirmed') AS confirmed,"
            " MIN(o.created) AS first_order, MAX(o.created) AS last_order,"
            " COALESCE(SUM(CASE WHEN o.status='confirmed' THEN COALESCE(o.delivery_fee,0)"
            "  + COALESCE((SELECT SUM(price*qty) FROM order_items WHERE order_id=o.id),0)"
            "  END),0) AS confirmed_total"
            " FROM orders o WHERE o.buyer = ?",
            (buyer,),
        ).fetchone()
    return {
        "buyer": buyer,
        "orders": int(row["orders"] or 0),
        "confirmed": int(row["confirmed"] or 0),
        "first_order": row["first_order"],
        "last_order": row["last_order"],
        "confirmed_total": round(row["confirmed_total"] or 0, 2),
    }


def list_customers(q="", limit=20):
    """Customers whose name contains ``q`` (autocomplete of the orders filter)."""
    q = _clean_buyer(q)[:60]
    like = "%" + re.sub(r"([\\%_])", r"\\\1", q) + "%"
    with database.live_db() as conn:
        rows = conn.execute(
            "SELECT ANY_VALUE(buyer) AS buyer, COUNT(*) AS orders,"
            " MAX(created) AS last_order,"
            " SUBSTRING_INDEX(GROUP_CONCAT(COALESCE(phone,'') ORDER BY created DESC"
            " SEPARATOR '|'), '|', 1) AS phone"
            " FROM orders WHERE buyer IS NOT NULL AND buyer <> '' AND buyer LIKE ?"
            " GROUP BY LOWER(buyer) ORDER BY last_order DESC LIMIT ?",
            (like, int(limit)),
        ).fetchall()
    return [
        {
            "buyer": r["buyer"],
            "orders": int(r["orders"]),
            "phone": r["phone"] or "",
            "last_order": r["last_order"],
        }
        for r in rows
    ]
