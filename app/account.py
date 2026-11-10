"""Admin profile: username, password, reset e-mail, shop phone and photo.

Every change requires the current password (a stolen session alone cannot
take the account over). Changing the password or the username signs out
every other session.
"""

import re

from . import catalog, config
from . import db as database
from .catalog import StoreError

_USERNAME_RE = re.compile(r"^[\w.@-]{3,40}$", re.UNICODE)
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")


def normalize_phone(raw):
    """International digits only (``212681771457``); Moroccan ``06...`` accepted."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 10:
        digits = "212" + digits[1:]
    if not (9 <= len(digits) <= 15):
        raise StoreError(400, "invalid_phone", "رقم الهاتف غير صالح (مثال: +212612345678)")
    return digits


def shop_phone(conn=None):
    if conn is None:
        with database.live_db() as c:
            return shop_phone(c)
    return database.get_meta(conn, "whatsapp") or config.WHATSAPP_NUMBER


def profile(conn=None):
    if conn is None:
        with database.live_db() as c:
            return profile(c)
    return {
        "username": database.get_meta(conn, "admin_user", ""),
        "email": database.get_meta(conn, "admin_email", ""),
        "phone": shop_phone(conn),
        "avatar": database.get_meta(conn, "admin_avatar", "") or "",
    }


def update_profile(payload, current_token):
    """Apply the changed fields of ``payload``; returns (profile, signed_out_others)."""
    current = str(payload.get("current_password", "") or "")
    if not current:
        raise StoreError(400, "missing_password", "أدخل كلمة المرور الحالية لتأكيد التغيير")

    username = payload.get("username")
    email = payload.get("email")
    phone = payload.get("phone")
    new_password = payload.get("new_password")

    if username is not None:
        username = str(username).strip()
        if not _USERNAME_RE.match(username):
            raise StoreError(
                400,
                "invalid_username",
                "اسم المستخدم من 3 إلى 40 حرفاً (حروف، أرقام، . _ - @) بدون مسافات",
            )
    if email is not None:
        email = str(email).strip().lower()
        if not _EMAIL_RE.match(email):
            raise StoreError(400, "invalid_email", "البريد الإلكتروني غير صالح")
    if phone is not None:
        phone = normalize_phone(str(phone))
    if new_password is not None:
        new_password = str(new_password)
        if len(new_password) < config.MIN_PASSWORD_LEN:
            raise StoreError(
                400,
                "weak_password",
                f"كلمة المرور يجب أن تتكون من {config.MIN_PASSWORD_LEN} أحرف على الأقل",
            )
        if len(new_password) > 256:
            raise StoreError(400, "weak_password", "كلمة المرور طويلة جداً")

    with database.db_lock, database.live_db() as conn:
        if not database.check_admin_password(conn, current):
            raise StoreError(403, "wrong_password", "كلمة المرور الحالية غير صحيحة")
        old_user = database.get_meta(conn, "admin_user", "")
        user_changed = username is not None and username != old_user
        if user_changed:
            database.set_meta(conn, "admin_user", username)
            conn.execute("UPDATE sessions SET user=?", (username,))
        if email is not None:
            database.set_meta(conn, "admin_email", email)
        phone_changed = phone is not None and phone != shop_phone(conn)
        if phone_changed:
            database.set_meta(conn, "whatsapp", phone)
        if new_password is not None:
            database.set_admin_password(conn, new_password)
        result = profile(conn)
    sign_out = new_password is not None or user_changed
    if sign_out:
        database.delete_all_sessions(except_token=current_token)
    if phone_changed:
        catalog.bump_catalog_version()  # the storefront settings carry the number
    return result, sign_out


def set_avatar(source):
    """Store the profile photo (data: URL, max 2 MB); returns the new profile."""
    content, ext = catalog.decode_data_url(str(source or ""), max_bytes=config.MAX_AVATAR_BYTES)
    url = catalog.save_upload(content, ext, prefix="avatar")
    with database.db_lock, database.live_db() as conn:
        old = database.get_meta(conn, "admin_avatar", "")
        database.set_meta(conn, "admin_avatar", url)
        result = profile(conn)
    if old and old != url:
        catalog.remove_stored_image(old)
    return result


def remove_avatar():
    with database.db_lock, database.live_db() as conn:
        old = database.get_meta(conn, "admin_avatar", "")
        database.set_meta(conn, "admin_avatar", "")
        result = profile(conn)
    if old:
        catalog.remove_stored_image(old)
    return result
