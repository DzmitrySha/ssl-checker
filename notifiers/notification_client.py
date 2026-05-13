"""Клиент корпоративного сервиса уведомлений (POST /api/v1/notifications)."""

from __future__ import annotations

import warnings
from typing import Any

import requests
from urllib3.exceptions import InsecureRequestWarning

from config.settings import (
    NOTIFICATION_API_BASE_URL,
    NOTIFICATION_API_TLS_VERIFY,
    NOTIFICATION_APP_LABEL,
    NOTIFICATION_CLIENT_SECRET_KEY,
    NOTIFICATION_DELIVER_TO_MATTERMOST,
    NOTIFICATION_USER_IDS,
    SEND_NOTIFICATIONS,
)
from core.logger import logger


def _parse_user_ids(raw: str) -> list[str]:
    return [p.strip() for p in raw.replace("\n", ",").split(",") if p.strip()]


def is_notification_service_configured() -> bool:
    if not (
        NOTIFICATION_API_BASE_URL.strip()
        and NOTIFICATION_CLIENT_SECRET_KEY.strip()
        and NOTIFICATION_APP_LABEL.strip()
    ):
        return False
    return len(_parse_user_ids(NOTIFICATION_USER_IDS)) > 0


def _format_api_error_body(r: requests.Response) -> str:
    text = (r.text or "").strip()
    ct = (r.headers.get("Content-Type") or "").lower()
    if "html" in ct or text.lower().startswith("<!doctype") or text.lower().startswith("<html"):
        return "<HTML страница ошибки — см. логи сервиса уведомлений или Swagger по формату запроса>"
    return text[:800]


def create_notification(*, title: str, text: str) -> bool:
    """POST /api/v1/notifications. Возвращает True при успешном ответе (2xx). Поле link не отправляется."""
    if not SEND_NOTIFICATIONS:
        logger.info("\n[SKIP Notification API]\n{}", text[:800])
        return False
    if not is_notification_service_configured():
        logger.warning(
            "[Notification API] Не заданы NOTIFICATION_API_BASE_URL, "
            "NOTIFICATION_CLIENT_SECRET_KEY, NOTIFICATION_APP_LABEL или пустой NOTIFICATION_USER_IDS."
        )
        return False

    base = NOTIFICATION_API_BASE_URL.strip().rstrip("/")
    url = f"{base}/api/v1/notifications"
    headers = {
        "clientSecretKey": NOTIFICATION_CLIENT_SECRET_KEY.strip(),
        "appLabel": NOTIFICATION_APP_LABEL.strip(),
        "Content-Type": "application/json",
    }
    user_sids = _parse_user_ids(NOTIFICATION_USER_IDS)
    body: dict[str, Any] = {
        "title": title,
        "text": text,
        "deliverToMattermost": NOTIFICATION_DELIVER_TO_MATTERMOST,
        "userSids": user_sids,
    }
    try:
        with warnings.catch_warnings():
            if NOTIFICATION_API_TLS_VERIFY is False:
                warnings.simplefilter("ignore", InsecureRequestWarning)
            r = requests.post(url, json=body, headers=headers, timeout=30, verify=NOTIFICATION_API_TLS_VERIFY)
        if 200 <= r.status_code < 300:
            logger.info("[Notification API] OK {}", r.status_code)
            return True
        logger.warning("[Notification API] {} {}", r.status_code, _format_api_error_body(r))
        if r.status_code >= 500:
            logger.info(
                "5xx — ошибка на стороне сервиса уведомлений или неверный формат запроса. "
                "Сверьте Swagger: заголовки clientSecretKey / appLabel, поля JSON (userSids, типы)."
            )
        elif r.status_code in (401, 403):
            logger.info("Проверьте NOTIFICATION_CLIENT_SECRET_KEY и NOTIFICATION_APP_LABEL.")
        return False
    except requests.RequestException as e:
        logger.warning(
            "[Уведомления] Не удалось связаться с API уведомлений ({}): {}. "
            "Проверка сертификатов узлов уже выполнена; текст отчёта — в логе выше.",
            url,
            e,
        )
        logger.opt(exception=True).debug("Детали ошибки запроса к API уведомлений:")
        err = str(e)
        if "CERTIFICATE_VERIFY" in err or "SSLCertVerificationError" in err:
            logger.info(
                "TLS к сервису уведомлений не прошёл проверку. "
                "NOTIFICATION_API_TLS_VERIFY=true — строго проверять TLS (нужен доверенный для Python корневой сертификат издателя). "
                "Для теста: false. Для прода: путь к PEM-файлу корня вашей организации."
            )
        return False
