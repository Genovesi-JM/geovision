"""Simple mail helper used by the forgot-password flow.

This attempts to send an email via SMTP using configuration in
`app.config.settings`. If SMTP is not configured, it writes the reset
link to `backend/reset_links.txt` so a developer/admin can copy it.
"""
from __future__ import annotations
import smtplib
from email.message import EmailMessage
from datetime import datetime
from pathlib import Path
from typing import Tuple

from .config import settings


def _load_html_template(reset_link: str) -> str | None:
    """Load the HTML reset template and inject the reset link."""
    try:
        template_path = Path(__file__).resolve().parents[2] / "emails" / "reset-password.html"
        html = template_path.read_text(encoding="utf-8")
        logo_url = (
            settings.frontend_base.rstrip("/") + "/assets/img/geovision-logo.png"
            if settings.frontend_base
            else ""
        )
        html = html.replace("{{reset_link}}", reset_link)
        if logo_url:
            html = html.replace("cid:geovision-logo", logo_url)
        return html
    except Exception:
        return None


def send_reset_email(to_email: str, reset_link: str) -> Tuple[bool, str]:
    """Send a password reset email.

    Returns (sent, info) where `sent` is True when the SMTP send succeeded
    (or when the link was written to a local file), and `info` contains a
    human-friendly note (or error).
    """
    subject = "GeoVision – Pedido de redefinição de palavra-passe"
    body = (
        "Pedido de redefinição de palavra-passe\n\n"
        "Abre o link abaixo para escolher uma nova palavra-passe.\n\n"
        f"{reset_link}\n\n"
        "Se não pediste esta redefinição, ignora esta mensagem."
    )

    # If SMTP is not configured, write the link to a local file for admins
    if not settings.smtp_host or not settings.smtp_from:
        try:
            path = "backend/reset_links.txt"
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(f"[{datetime.utcnow().isoformat()}] to={to_email} link={reset_link}\n")
            return True, f"SMTP não configurado – link escrito em {path}"
        except Exception as exc:
            return False, f"Falha a escrever link em ficheiro: {exc}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.set_content(body)

    html = _load_html_template(reset_link)
    if html:
        msg.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(host=settings.smtp_host, port=settings.smtp_port, timeout=10) as s:
            s.ehlo()
            if settings.smtp_use_tls and settings.smtp_user and settings.smtp_password:
                s.starttls()
            if settings.smtp_user and settings.smtp_password:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return True, "Email enviado"
    except Exception as exc:
        return False, f"Falha ao enviar email: {exc}"
