"""Notification provider implementations and lazy factory."""

from .factory import create_notification_provider, default_email_log_path

__all__ = ["create_notification_provider", "default_email_log_path"]
