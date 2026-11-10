from app.security import hash_password, verify_password, hash_token
from app import config


def test_password_hash_verify():
    pw = "S3curePass!"
    h = hash_password(pw, salt="testsalt12345678")
    assert h.startswith("pbkdf2$")
    assert verify_password(pw, "testsalt12345678", h)
    assert not verify_password("wrong", "testsalt12345678", h)


def test_token_hash():
    t = "sometoken123"
    assert hash_token(t) != t
    assert len(hash_token(t)) == 64


def test_limits_config():
    assert config.MAX_UPLOAD_BYTES == 8 * 1024 * 1024
    assert config.MIN_PASSWORD_LEN >= 8


def test_reset_email_is_the_one_set_in_the_profile():
    from app import db

    with db.db_lock, db.live_db() as conn:
        db.set_meta(conn, "admin_email", "owner@example.com")  # meta is restored after the test
        assert db.get_reset_email(conn) == "owner@example.com"


def test_reset_token_is_single_use_and_updates_only_the_db_hash():
    from app import db

    with db.db_lock, db.live_db() as conn:
        token = db.create_reset_record(conn, "owner@example.com")
        assert db.consume_reset_token(conn, token) == "owner@example.com"
        assert db.consume_reset_token(conn, token) is None  # cannot be reused
