"""E-mail delivery for the password-reset flow.

Uses the SMTP settings from ``app.config``. When SMTP is not configured the
reset link is printed to the server console instead so the flow remains
testable locally; callers must then surface the link to the operator.
"""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from . import config, logs

log = logs.get("mail")


def send_password_reset(to_email, reset_link):
    """Send the reset e-mail; returns True when accepted by a mail server."""
    subject = "فيه شفاء — Réinitialisation du mot de passe admin"
    body = (
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

    if not (config.SMTP_HOST and config.EMAIL_FROM):
        # Development/on-prem fallback: log the link so the operator can forward it.
        log.warning("SMTP not configured: password-reset link", extra={"link": reset_link})
        return True

    to_email = to_email or config.DEFAULT_ADMIN_EMAIL
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(body, "html", "utf-8"))

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
        return True
    except Exception as exc:  # pragma: no cover - depends on external servers
        log.error("password-reset e-mail failed", extra={"to": to_email, "error": str(exc)})
        return False
