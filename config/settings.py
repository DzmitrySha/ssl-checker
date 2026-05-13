"""Конфигурация SSL-монитора (из .env через python-dotenv)."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from .env_parsers import env_bool, env_int, env_str

load_dotenv()

LANGUAGE = env_str("LANGUAGE", "ru").strip().lower()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_logs_dir_raw = env_str("LOGS_DIR", "").strip()
LOGS_DIR = Path(_logs_dir_raw).expanduser().resolve() if _logs_dir_raw else _PROJECT_ROOT / "logs"


# Примеры имён в .env: SITES_TO_CHECK, SITE_PORT, WARN_DAYS ...
SITE_PORT = env_int("SITE_PORT", 443)
# Один или несколько узлов: через запятую и/или с новой строки; допускается host:8443.
# Если задан SITES_FILE и файл существует — список читается из файла, иначе из этой строки.
SITES_TO_CHECK = env_str("SITES_TO_CHECK", "google.com,ya.ru")
SITES_FILE = env_str("SITES_FILE", "")

# Пороги (календарные дни до даты окончания в сертификате): < 7 — предупреждение, < 3 — критично, <= 0 — просрочен
WARN_DAYS = env_int("WARN_DAYS", 7)
CRITICAL_DAYS = env_int("CRITICAL_DAYS", 3)

SEND_WIN_ALERT = env_bool("SEND_WIN_ALERT", True)
WIN_USE_NATIVE_MSGBOX = env_bool("WIN_USE_NATIVE_MSGBOX", True)
# Корпоративный сервис уведомлений → POST /api/v1/notifications (заголовки clientSecretKey, appLabel)
SEND_NOTIFICATIONS = env_bool("SEND_NOTIFICATIONS", False)
NOTIFICATION_API_BASE_URL = env_str("NOTIFICATION_API_BASE_URL", "https://notification-test.energo.net")
NOTIFICATION_CLIENT_SECRET_KEY = env_str("NOTIFICATION_CLIENT_SECRET_KEY", "")
NOTIFICATION_APP_LABEL = env_str("NOTIFICATION_APP_LABEL", "")
# ID пользователей-получателей через запятую или с новой строки (в JSON уходит как userSids).
NOTIFICATION_USER_IDS = env_str("NOTIFICATION_USER_IDS", "")
NOTIFICATION_DELIVER_TO_MATTERMOST = env_bool("NOTIFICATION_DELIVER_TO_MATTERMOST", True)
# Проверка TLS при POST: true | false | путь к PEM корневого сертификата издателя (центра сертификации)
_notif_tls_raw = env_str("NOTIFICATION_API_TLS_VERIFY", "true")
if _notif_tls_raw.lower() in {"true", "1", "yes", "y", "on"}:
    NOTIFICATION_API_TLS_VERIFY: bool | str = True
elif _notif_tls_raw.lower() in {"false", "0", "no", "n", "off"}:
    NOTIFICATION_API_TLS_VERIFY = False
else:
    NOTIFICATION_API_TLS_VERIFY = _notif_tls_raw

# Проверка цепочки доверия к узлу: true | путь к PEM/CRT корня издателя | false
# PEM — текстовый формат сертификата; .crt часто тоже PEM внутри. DER: конвертация через openssl.
# Корневой PEM не заменяет самоподписанный сертификат сайта: узел должен выдать цепочку, подписанную этим издателем.
_tls_verify_raw = env_str("TLS_VERIFY", "true")
if _tls_verify_raw.lower() in {"true", "1", "yes", "y", "on"}:
    TLS_VERIFY: bool | str = True
elif _tls_verify_raw.lower() in {"false", "0", "no", "n", "off"}:
    TLS_VERIFY = False
else:
    TLS_VERIFY = _tls_verify_raw

# Если True — доверять только PEM из TLS_VERIFY (без системных корней Windows).
# Если False — системные корни + PEM из TLS_VERIFY (если путь задан).
TLS_SITE_CHECK_TRUST_ONLY_CAFILE = env_bool("TLS_SITE_CHECK_TRUST_ONLY_CAFILE", False)
TLS_READ_EXPIRY_ON_VERIFY_FAIL = env_bool("TLS_READ_EXPIRY_ON_VERIFY_FAIL", True)

# Режим `python main.py --schedule`: IANA-таймзона (нужен пакет tzdata в образе Docker)
SCHEDULER_TIMEZONE = env_str("SCHEDULER_TIMEZONE", "Europe/Moscow")
DAILY_BATCH_HOUR = env_int("DAILY_BATCH_HOUR", 9)
DAILY_BATCH_MINUTE = env_int("DAILY_BATCH_MINUTE", 0)
RUN_BATCH_ON_START = env_bool("RUN_BATCH_ON_START", True)
