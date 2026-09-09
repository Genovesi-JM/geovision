"""Backward-compatible email templates and sending helpers for GeoVision.

Supports:
- Password reset emails
- Payment confirmation
- User invitation (join company)
- Order status updates
- Critical alerts

Delivery is delegated to the notifications provider boundary. Local and
development environments retain the historical file fallback.
"""
from __future__ import annotations
from typing import Tuple

from .core.time import utc_now
from .integrations.notifications import (
    create_notification_provider,
    default_email_log_path,
)
from .modules.notifications.ports import NotificationProvider
from .modules.notifications.services import NotificationService


# ═══════════════════════════════════════════════════════════════
# Base HTML template
# ═══════════════════════════════════════════════════════════════

def _base_html(title: str, content: str) -> str:
    """Professional HTML email wrapper matching GeoVision brand."""
    return f"""<!DOCTYPE html>
<html lang="pt">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:'Segoe UI',Roboto,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:40px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
<tr><td style="background:linear-gradient(135deg,#1a5276,#2e86c1);padding:30px 40px;text-align:center;">
<h1 style="margin:0;color:#fff;font-size:24px;font-weight:600;">GeoVision</h1>
<p style="margin:4px 0 0;color:rgba(255,255,255,0.8);font-size:13px;">Geospatial Intelligence Platform</p>
</td></tr>
<tr><td style="padding:40px;">
{content}
</td></tr>
<tr><td style="background:#f8f9fa;padding:20px 40px;text-align:center;border-top:1px solid #e9ecef;">
<p style="margin:0;color:#6c757d;font-size:12px;">
© {utc_now().year} GeoVision Ops · Angola
<br>Este email foi enviado automaticamente. Não responda directamente.
</p>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""


# ═══════════════════════════════════════════════════════════════
# Email Templates
# ═══════════════════════════════════════════════════════════════

def _reset_password_html(reset_link: str) -> str:
    content = f"""
    <h2 style="margin:0 0 20px;color:#1a5276;font-size:20px;">Redefinição de Palavra-passe</h2>
    <p style="color:#333;line-height:1.6;">Recebemos um pedido para redefinir a sua palavra-passe.
    Clique no botão abaixo para criar uma nova palavra-passe:</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;">
    <tr><td align="center">
    <a href="{reset_link}" style="display:inline-block;background:#2e86c1;color:#fff;padding:14px 40px;border-radius:8px;text-decoration:none;font-weight:600;font-size:16px;">
    Redefinir Palavra-passe</a>
    </td></tr></table>
    <p style="color:#666;font-size:13px;line-height:1.6;">Este link expira em <strong>1 hora</strong>.
    Se não pediu esta redefinição, ignore este email.</p>
    <p style="color:#999;font-size:12px;margin-top:20px;word-break:break-all;">Link directo: {reset_link}</p>
    """
    return _base_html("Redefinição de Palavra-passe", content)


def _payment_confirmation_html(order_number: str, amount: str, currency: str, method: str) -> str:
    content = f"""
    <h2 style="margin:0 0 20px;color:#1a5276;font-size:20px;">Confirmação de Pagamento</h2>
    <p style="color:#333;line-height:1.6;">O seu pagamento foi recebido com sucesso!</p>
    <table style="width:100%;margin:20px 0;border-collapse:collapse;">
    <tr><td style="padding:10px;border-bottom:1px solid #eee;color:#666;">Pedido</td>
    <td style="padding:10px;border-bottom:1px solid #eee;color:#333;font-weight:600;">{order_number}</td></tr>
    <tr><td style="padding:10px;border-bottom:1px solid #eee;color:#666;">Valor</td>
    <td style="padding:10px;border-bottom:1px solid #eee;color:#333;font-weight:600;">{amount} {currency}</td></tr>
    <tr><td style="padding:10px;border-bottom:1px solid #eee;color:#666;">Método</td>
    <td style="padding:10px;border-bottom:1px solid #eee;color:#333;">{method}</td></tr>
    </table>
    <p style="color:#333;line-height:1.6;">Pode acompanhar o estado do seu pedido no dashboard.</p>
    """
    return _base_html("Confirmação de Pagamento", content)


def _invite_user_html(inviter_name: str, company_name: str, invite_link: str) -> str:
    content = f"""
    <h2 style="margin:0 0 20px;color:#1a5276;font-size:20px;">Convite para GeoVision</h2>
    <p style="color:#333;line-height:1.6;"><strong>{inviter_name}</strong> convidou-o a juntar-se à
    equipa <strong>{company_name}</strong> na plataforma GeoVision.</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;">
    <tr><td align="center">
    <a href="{invite_link}" style="display:inline-block;background:#2e86c1;color:#fff;padding:14px 40px;border-radius:8px;text-decoration:none;font-weight:600;font-size:16px;">
    Aceitar Convite</a>
    </td></tr></table>
    <p style="color:#666;font-size:13px;">Este convite expira em 7 dias.</p>
    """
    return _base_html("Convite para GeoVision", content)


def _order_status_html(order_number: str, status: str, message: str) -> str:
    status_colors = {
        "confirmed": "#27ae60", "processing": "#f39c12",
        "shipped": "#2e86c1", "completed": "#27ae60",
        "cancelled": "#e74c3c",
    }
    color = status_colors.get(status, "#333")
    content = f"""
    <h2 style="margin:0 0 20px;color:#1a5276;font-size:20px;">Atualização do Pedido</h2>
    <p style="color:#333;line-height:1.6;">O seu pedido <strong>{order_number}</strong> tem uma atualização:</p>
    <div style="background:#f8f9fa;border-left:4px solid {color};padding:15px 20px;margin:20px 0;border-radius:4px;">
    <p style="margin:0;color:{color};font-weight:600;font-size:16px;">{status.upper()}</p>
    <p style="margin:8px 0 0;color:#333;">{message}</p>
    </div>
    """
    return _base_html("Atualização do Pedido", content)


def _critical_alert_html(title: str, description: str, location: str, severity: str) -> str:
    content = f"""
    <h2 style="margin:0 0 20px;color:#e74c3c;font-size:20px;">⚠ Alerta {severity.upper()}</h2>
    <div style="background:#fdf2f2;border-left:4px solid #e74c3c;padding:15px 20px;margin:20px 0;border-radius:4px;">
    <p style="margin:0;font-weight:600;color:#c0392b;">{title}</p>
    <p style="margin:8px 0 0;color:#333;">{description}</p>
    <p style="margin:8px 0 0;color:#666;font-size:13px;">📍 {location}</p>
    </div>
    <p style="color:#333;line-height:1.6;">Aceda ao dashboard para mais detalhes e ações recomendadas.</p>
    """
    return _base_html(f"Alerta {severity.upper()}", content)


# ═══════════════════════════════════════════════════════════════
# Send functions
# ═══════════════════════════════════════════════════════════════

def _send_email(
    to_email: str,
    subject: str,
    plain_text: str,
    html: str | None = None,
    provider: NotificationProvider | None = None,
) -> Tuple[bool, str]:
    """Send through the notification boundary and preserve the legacy result."""
    try:
        selected_provider = (
            provider if provider is not None else create_notification_provider()
        )
        result = NotificationService(selected_provider).send_email(
            recipient=to_email,
            subject=subject,
            plain_text=plain_text,
            html=html,
        )
    except Exception:
        # Configuration and provider details must never reach API responses.
        return False, "Falha ao enviar email"

    if result.ok:
        if result.provider == "file":
            path = getattr(selected_provider, "log_path", default_email_log_path())
            return True, f"SMTP não configurado – log escrito em {path}"
        return True, "Email enviado"

    failure_code = result.failure.code if result.failure else ""
    if failure_code == "notification_log_failed":
        return False, "Falha a escrever log"
    if failure_code in {
        "notification_provider_disabled",
        "notification_provider_not_allowed",
        "smtp_auth_not_configured",
        "smtp_not_configured",
        "smtp_tls_required",
        "unsupported_notification_provider",
    }:
        return False, "SMTP não configurado"
    return False, "Falha ao enviar email"


def send_reset_email(to_email: str, reset_link: str) -> Tuple[bool, str]:
    subject = "GeoVision – Redefinição de palavra-passe"
    plain = f"Redefinir palavra-passe: {reset_link}\nExpira em 1 hora."
    html = _reset_password_html(reset_link)
    return _send_email(to_email, subject, plain, html)


def send_payment_confirmation(to_email: str, order_number: str, amount: str, currency: str = "AOA", method: str = "Multicaixa") -> Tuple[bool, str]:
    subject = f"GeoVision – Pagamento confirmado ({order_number})"
    plain = f"Pagamento confirmado para pedido {order_number}: {amount} {currency} via {method}."
    html = _payment_confirmation_html(order_number, amount, currency, method)
    return _send_email(to_email, subject, plain, html)


def send_user_invite(to_email: str, inviter_name: str, company_name: str, invite_link: str) -> Tuple[bool, str]:
    subject = f"GeoVision – Convite de {inviter_name} para {company_name}"
    plain = f"{inviter_name} convidou-o para {company_name} na GeoVision. Aceitar: {invite_link}"
    html = _invite_user_html(inviter_name, company_name, invite_link)
    return _send_email(to_email, subject, plain, html)


def send_order_status(to_email: str, order_number: str, status: str, message: str) -> Tuple[bool, str]:
    subject = f"GeoVision – Pedido {order_number}: {status}"
    plain = f"Pedido {order_number} atualizado para {status}. {message}"
    html = _order_status_html(order_number, status, message)
    return _send_email(to_email, subject, plain, html)


def send_critical_alert(to_email: str, title: str, description: str, location: str = "", severity: str = "critical") -> Tuple[bool, str]:
    subject = f"GeoVision – ALERTA {severity.upper()}: {title}"
    plain = f"ALERTA {severity.upper()}: {title}\n{description}\nLocal: {location}"
    html = _critical_alert_html(title, description, location, severity)
    return _send_email(to_email, subject, plain, html)
