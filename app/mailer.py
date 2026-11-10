"""E-mail delivery for the password-reset flow.

Delivery order (see ``app.config``):

1. Resend HTTPS API when ``FIHI_RESEND_API_KEY`` is set. It works on every
   Railway plan (Railway blocks outbound SMTP below the Pro plan).
2. SMTP when ``FIHI_SMTP_HOST`` and ``FIHI_EMAIL_FROM`` are set.
3. Otherwise the reset link is written to the server logs, so the flow stays
   usable locally.
"""

import json
import smtplib
import ssl
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from . import config, logs

log = logs.get("mail")

RESEND_URL = "https://api.resend.com/emails"
# Resend's shared sender: usable before the shop's domain is verified, but it
# only delivers to the address that owns the Resend account.
RESEND_FALLBACK_FROM = "fihi-chifae <onboarding@resend.dev>"


def _reset_body(reset_link):
    return (
        (
            "<div style='font-family:Arial,sans-serif;max-width:520px;margin:auto;color:#1f2937'>"
            "<h2>Réinitialisation du mot de passe admin</h2>"
            "<p>Vous avez demandé la réinitialisation du mot de passe de votre espace admin "
            "<b>fihi-chifae</b>.</p>"
            "<p>Cliquez sur le bouton ci-dessous : il expire dans "
            "<b>{ttl_min} minutes</b> et ne peut être utilisé qu'une seule fois.</p>"
            "<p style='text-align:center'>"
            '<a href="{link}" style=\'display:inline-block;background:#16a34a;color:#ffffff;'
            "padding:12px 26px;border-radius:8px;text-decoration:none;font-weight:bold'>"
            "Réinitialiser le mot de passe</a></p>"
            "<p style='font-size:12px;color:#6b7280'>Si le bouton ne s'ouvre pas, "
            "copiez ce lien :<br>"
            "{link}</p>"
            "<p style='font-size:12px;color:#6b7280'>Si vous n'êtes pas à l'origine "
            "de cette demande, ignorez cet e-mail.</p></div>"
        )
        .replace("{link}", reset_link)
        .replace("{ttl_min}", str(config.RESET_TOKEN_TTL_MS // 60000))
    )


def _send_resend(to_email, subject, html):
    sender = config.EMAIL_FROM or RESEND_FALLBACK_FROM
    status = _post_resend(sender, to_email, subject, html)
    if status == 403 and sender != RESEND_FALLBACK_FROM:
        # the shop domain is not verified at Resend yet: use the shared sender
        # meanwhile (switches back by itself once the domain is verified)
        log.warning("shop domain not verified at Resend yet: using the shared sender")
        status = _post_resend(RESEND_FALLBACK_FROM, to_email, subject, html)
    return status == 200


def _post_resend(sender, to_email, subject, html):
    """POST one e-mail; returns 200 when accepted, else the HTTP status (0: network)."""
    payload = {"from": sender, "to": [to_email], "subject": subject, "html": html}
    req = urllib.request.Request(  # noqa: S310 - fixed https URL
        RESEND_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + config.RESEND_API_KEY,
            "Content-Type": "application/json",
            "User-Agent": "fihi-chifae",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - fixed https URL
            msg_id = json.load(resp).get("id")
        log.info("password-reset e-mail sent", extra={"to": to_email, "id": msg_id})
        return 200
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode("utf-8", "replace") if exc.fp else ""
        log.error(
            "password-reset e-mail refused by Resend",
            extra={"to": to_email, "from": sender, "status": exc.code, "error": detail},
        )
        return exc.code
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.error("password-reset e-mail failed", extra={"to": to_email, "error": str(exc)})
    return 0


def _send_smtp(to_email, subject, html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        if config.SMTP_USE_TLS:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as s:
                s.starttls(context=ssl.create_default_context())
                if config.SMTP_USER:
                    s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as s:
                if config.SMTP_USER:
                    s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
        log.info("password-reset e-mail sent", extra={"to": to_email, "via": "smtp"})
        return True
    except Exception as exc:  # pragma: no cover - depends on external servers
        log.error("password-reset e-mail failed", extra={"to": to_email, "error": str(exc)})
        return False


def send_password_reset(to_email, reset_link):
    """Send the reset e-mail; returns True when accepted for delivery."""
    to_email = to_email or config.DEFAULT_ADMIN_EMAIL
    subject = "فيه شفاء — Réinitialisation du mot de passe admin"
    html = _reset_body(reset_link)
    if config.RESEND_API_KEY:
        return _send_resend(to_email, subject, html)
    if config.SMTP_HOST and config.EMAIL_FROM:
        return _send_smtp(to_email, subject, html)
    # Development/on-prem fallback: log the link so the operator can forward it.
    log.warning("no e-mail service configured: password-reset link", extra={"link": reset_link})
    return True
