"""Send newsletter HTML via SMTP (or MailHog for testing)."""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger("emailer")


def send_newsletter(
    html: str,
    subject: str,
    dry_run: bool = False,
) -> dict:
    """Send newsletter email via SMTP."""
    recipients = settings.to_emails_list

    if dry_run:
        log.info("emailer.dry_run", subject=subject, recipients=recipients)
        return {"sent": False, "reason": "dry_run", "recipients": recipients}

    if not settings.smtp_host:
        log.warning("emailer.no_smtp_configured")
        return {"sent": False, "reason": "no_smtp_host"}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.from_email
    msg["To"] = ", ".join(recipients)

    # Plain text fallback
    plain = "This newsletter is best viewed in HTML. Please enable HTML viewing."
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if settings.smtp_tls:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
            server.starttls()
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)

        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_pass)

        server.sendmail(settings.from_email, recipients, msg.as_string())
        server.quit()

        log.info("emailer.sent", subject=subject, recipients=recipients)
        return {"sent": True, "recipients": recipients}

    except Exception as exc:
        log.error("emailer.send_error", error=str(exc))
        return {"sent": False, "error": str(exc)}
