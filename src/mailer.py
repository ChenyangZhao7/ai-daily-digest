from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def send_email(
    subject: str, html: str, cfg: dict, password: str | None = None
) -> None:
    password = password or os.environ.get("QQ_SMTP_AUTH_CODE")
    if not password:
        raise RuntimeError("QQ_SMTP_AUTH_CODE is not set")
    email_cfg = cfg["email"]
    if not email_cfg.get("to") or not email_cfg.get("from"):
        raise RuntimeError("MAIL_TO / MAIL_FROM are not configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = email_cfg["from"]
    message["To"] = email_cfg["to"]
    message.set_content(html, subtype="html")

    with smtplib.SMTP_SSL(
        email_cfg["smtp_host"], email_cfg["smtp_port"], timeout=20
    ) as server:
        server.login(email_cfg["from"], password)
        server.send_message(message)
