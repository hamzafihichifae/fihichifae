"""Password-reset e-mail delivery (Resend HTTPS API, placeholder address)."""

import json

import pytest

from app import config, mailer
from app import db as database


class _Resp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self, *_):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append((req.full_url, dict(req.header_items()), json.loads(req.data)))
        return _Resp({"id": "msg_1"})

    monkeypatch.setattr(mailer.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_reset_mail_goes_through_resend_when_a_key_is_set(monkeypatch, sent):
    monkeypatch.setattr(config, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(config, "EMAIL_FROM", "Fihi Chifae <no-reply@fihichifae.com>")
    assert mailer.send_password_reset("owner@example.com", "https://shop/reset?token=abc")
    url, headers, body = sent[0]
    assert url == mailer.RESEND_URL
    assert headers["Authorization"] == "Bearer re_test"
    assert body["to"] == ["owner@example.com"]
    assert body["from"] == "Fihi Chifae <no-reply@fihichifae.com>"
    assert "https://shop/reset?token=abc" in body["html"]


def test_unverified_domain_uses_the_resend_shared_sender(monkeypatch, sent):
    monkeypatch.setattr(config, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(config, "EMAIL_FROM", "")
    assert mailer.send_password_reset("owner@example.com", "https://shop/r")
    assert sent[0][2]["from"] == mailer.RESEND_FALLBACK_FROM


def test_refused_mail_returns_false(monkeypatch):
    def refuse(req, timeout=None):
        raise mailer.urllib.error.HTTPError(req.full_url, 403, "forbidden", {}, None)

    monkeypatch.setattr(config, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(mailer.urllib.request, "urlopen", refuse)
    assert mailer.send_password_reset("owner@example.com", "https://shop/r") is False


def test_without_any_service_the_link_is_only_logged(monkeypatch, sent):
    monkeypatch.setattr(config, "RESEND_API_KEY", "")
    monkeypatch.setattr(config, "SMTP_HOST", "")
    assert mailer.send_password_reset("owner@example.com", "https://shop/r")
    assert sent == []


def test_placeholder_reset_address_is_replaced_but_a_chosen_one_is_kept():
    with database.db_lock, database.live_db() as conn:  # meta is restored after the test
        database.set_meta(conn, "admin_email", "admin@fihi-chifae.com")
        database.init_admin(conn)
        assert database.get_reset_email(conn) == config.DEFAULT_ADMIN_EMAIL.lower()

        database.set_meta(conn, "admin_email", "owner@example.com")
        database.init_admin(conn)
        assert database.get_reset_email(conn) == "owner@example.com"
