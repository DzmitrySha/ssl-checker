"""Точка входа для отправки в корпоративный сервис уведомлений."""

from __future__ import annotations

from config.settings import SEND_NOTIFICATIONS
from core.logger import logger
from notifiers.notification_client import create_notification, is_notification_service_configured


def send_user_notification(text: str, *, title: str = "SSL Checker") -> bool:
    if not SEND_NOTIFICATIONS:
        logger.info("\n[SKIP Уведомления]\n{}", text[:800])
        return False
    if is_notification_service_configured():
        return create_notification(title=title, text=text)
    logger.warning(
        "SEND_NOTIFICATIONS=true, но не заданы полностью: "
        "NOTIFICATION_API_BASE_URL, NOTIFICATION_CLIENT_SECRET_KEY, "
        "NOTIFICATION_APP_LABEL, NOTIFICATION_USER_IDS (хотя бы один id)."
    )
    return False


def is_any_remote_send_configured() -> bool:
    return SEND_NOTIFICATIONS and is_notification_service_configured()
