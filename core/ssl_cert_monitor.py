"""Мониторинг срока TLS-сертификата узла + опционально сервис уведомлений.
Не называйте файл ssl.py — перекрывает стандартный модуль ssl."""
from __future__ import annotations

import json
import socket
import ssl
from datetime import datetime, timezone
from typing import NamedTuple

try:
    from cryptography import x509 as cryptography_x509
    from cryptography.hazmat.backends import default_backend as cryptography_default_backend
except ImportError:
    cryptography_x509 = None
    cryptography_default_backend = None

from config.settings import (
    SITE_PORT,
    TLS_READ_EXPIRY_ON_VERIFY_FAIL,
    TLS_SITE_CHECK_TRUST_ONLY_CAFILE,
    TLS_VERIFY,
)
from core.error_messages import build_error_dialog
from core.logger import logger
from core.models import AlertKind, CheckResult, ErrorCode
from core.site_list import load_site_entries, normalize_host_port
from core.status_policy import (
    CERT_DATE_CHAIN_NOTE,
    build_status_output,
    format_error_notification_markdown,
)
from notifiers.notify import send_user_notification
from notifiers.windows_notifier import show_window_alert

_TLS_TIMEOUT_SEC = 10.0


class NoPeerCertError(OSError):
    """Сервер не прислал сертификат (DER) при установлении TLS."""


class PeerCertSummary(NamedTuple):
    not_before_utc: datetime
    not_after_utc: datetime
    subject: str
    issuer: str


def _verify_log_caption(verify: bool | str) -> str:
    if verify is False:
        return "режим TLS_VERIFY=false (цепочка доверия не проверяется)"
    if isinstance(verify, str):
        return f"TLS_VERIFY — дополнительный корневой PEM: {verify}"
    return "TLS_VERIFY=true (системные корневые сертификаты Windows)"


def _cert_datetime_display(dt: datetime) -> str:
    """Дата/время окончания (или начала) действия для отображения — без суффикса UTC."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _dt_utc_from_crypto(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _peer_summary_from_der(der: bytes) -> PeerCertSummary:
    if cryptography_x509 is None or cryptography_default_backend is None:
        raise RuntimeError("Нужен пакет cryptography для разбора сертификата")
    cert = cryptography_x509.load_der_x509_certificate(der, cryptography_default_backend())
    nb_raw = getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before
    na_raw = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
    nb = _dt_utc_from_crypto(nb_raw)
    na = _dt_utc_from_crypto(na_raw)
    subject = cert.subject.rfc4514_string()
    issuer = cert.issuer.rfc4514_string()
    return PeerCertSummary(nb, na, subject, issuer)


def _read_peer_summary(host: str, port: int, ctx: ssl.SSLContext) -> PeerCertSummary:
    with socket.create_connection((host, port), timeout=_TLS_TIMEOUT_SEC) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
            if not der:
                raise NoPeerCertError("no_peer_cert")
            return _peer_summary_from_der(der)


# ========= TLS: хост, контекст, чтение сертификата =========
def _tls_context(verify: bool | str) -> ssl.SSLContext:
    if verify is False:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    if isinstance(verify, str):
        if TLS_SITE_CHECK_TRUST_ONLY_CAFILE:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
            ctx.load_verify_locations(cafile=verify)
            return ctx
        # Иначе: системные корни Windows + PEM-файл корня издателя — см. TLS_SITE_CHECK_TRUST_ONLY_CAFILE
        ctx = ssl.create_default_context()
        ctx.load_verify_locations(cafile=verify)
        return ctx
    return ssl.create_default_context()


def check_ssl_expiry(
    site: str,
    *,
    site_port: int = SITE_PORT,
    tls_verify: bool | str | None = None,
) -> CheckResult:
    verify = TLS_VERIFY if tls_verify is None else tls_verify
    host, port = normalize_host_port(site, site_port)
    logger.info("Проверка TLS: {}:{}, {}", host, port, _verify_log_caption(verify))

    def ok_pack(peer: PeerCertSummary, chain_trusted: bool) -> CheckResult:
        expiry_utc = peer.not_after_utc
        today = datetime.now(timezone.utc).date()
        end_d = expiry_utc.astimezone(timezone.utc).date()
        days = (end_d - today).days
        line = _cert_datetime_display(expiry_utc)
        if not chain_trusted:
            line += CERT_DATE_CHAIN_NOTE
        not_before_line = _cert_datetime_display(peer.not_before_utc)
        logger.info(
            "Сертификат {}:{} — дата окончания (UTC): {}, осталось календарных дней: {}",
            host,
            port,
            line,
            days,
        )
        return CheckResult(
            host=host,
            port=port,
            success=True,
            days_left=days,
            not_after_line=line,
            chain_ok=chain_trusted,
            error_code=None,
            subject=peer.subject or None,
            issuer=peer.issuer or None,
            not_before_line=not_before_line,
        )

    ctx = _tls_context(verify)
    try:
        return ok_pack(_read_peer_summary(host, port, ctx), verify is not False)
    except ssl.SSLError as e:
        if isinstance(verify, str):
            logger.info(
                "Указанный в TLS_VERIFY файл — это корневой сертификат центра сертификации (издателя). "
                "Доверяются только цепочки, которые этим издателем подписаны. Самоподписанный сертификат сайта "
                "(часто «Kubernetes Ingress … Fake Certificate») таким файлом «не лечится» — на сервере нужен "
                "сертификат, выпущенный вашим центром сертификации или публичным доверенным издателем."
            )
        if TLS_READ_EXPIRY_ON_VERIFY_FAIL and verify is not False:
            logger.warning("Строгая проверка TLS для {}:{} не прошла: {}", host, port, e)
            logger.info("Повторное подключение без проверки цепочки — только чтение срока с сертификата сайта.")
            try:
                return ok_pack(_read_peer_summary(host, port, _tls_context(False)), False)
            except (ssl.SSLError, OSError, TimeoutError, socket.timeout) as e2:
                logger.error("Повторная попытка для {}:{} не удалась: {}", host, port, e2)
            except (RuntimeError, ValueError) as e2:
                logger.error(
                    "Разбор сертификата (cryptography) для {}:{}: {}",
                    host,
                    port,
                    e2,
                )
                return CheckResult(host, port, False, None, None, False, ErrorCode.CERT_PARSE_FAILED)
        else:
            logger.error("Ошибка TLS при подключении к {}:{}: {}", host, port, e)
        logger.info(
            "Подсказка: TLS_VERIFY — true (системные корни Windows), false или путь к PEM корневого сертификата издателя."
        )
        return CheckResult(host, port, False, None, None, False, ErrorCode.SSL_VERIFY_FAILED)
    except (TimeoutError, socket.timeout):
        logger.error(
            "Таймаут TLS для {}:{} (ожидание ответа {:.0f} с).",
            host,
            port,
            _TLS_TIMEOUT_SEC,
        )
        return CheckResult(host, port, False, None, None, False, ErrorCode.TIMEOUT)
    except NoPeerCertError:
        logger.error("Узел {}:{} не прислал сертификат при TLS-рукопожатии.", host, port)
        return CheckResult(host, port, False, None, None, False, ErrorCode.NO_PEER_CERT)
    except OSError as e:
        logger.error("Ошибка сети или сокета {}:{}: {}", host, port, e)
        return CheckResult(host, port, False, None, None, False, ErrorCode.CONNECTION_ERROR)
    except (RuntimeError, ValueError) as e:
        logger.error("Не удалось разобрать сертификат {}:{} (библиотека cryptography): {}", host, port, e)
        return CheckResult(host, port, False, None, None, False, ErrorCode.CERT_PARSE_FAILED)


def _api_notification_title_error(host: str, dialog_title: str) -> str:
    return f"{dialog_title} — {host}"


def _api_notification_title_status(host: str, output_title: str) -> str:
    t = output_title.strip()
    return f"{t} — {host}" if t else f"Проверка TLS — {host}"


# ========= main =========
def run_monitor(
    *,
    site: str | None = None,
    site_port: int = SITE_PORT,
    as_json: bool = False,
    force_notify_always: bool = False,
) -> CheckResult:
    if site:
        entries = [normalize_host_port(site, site_port)]
    else:
        entries = load_site_entries()

    results: list[CheckResult] = []
    for host, port in entries:
        results.append(check_ssl_expiry(host, site_port=port))

    if as_json:
        if len(results) == 1:
            print(json.dumps(results[0].to_dict(), ensure_ascii=False, indent=2))
        else:
            print(json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2))
        return results[-1]

    for result in results:
        if not result.success:
            title, body = build_error_dialog(result.error_code or ErrorCode.UNKNOWN_ERROR, result.host)
            api_title = _api_notification_title_error(result.host, title)
            send_user_notification(
                format_error_notification_markdown(title=title, host=result.host, body=body),
                title=api_title,
            )
            show_window_alert(title, body, kind=AlertKind.ERROR)
            return result

        output = build_status_output(
            result.host,
            result.days_left or 0,
            result.not_after_line or "",
            result.chain_ok,
            subject=result.subject,
            issuer=result.issuer,
            not_before_line=result.not_before_line,
        )
        logger.info("\n{}", output.body)
        if output.kind is not AlertKind.NONE:
            send_user_notification(
                output.notify_text,
                title=_api_notification_title_status(result.host, output.title),
            )
            show_window_alert(output.title, output.body, kind=output.kind)
        elif force_notify_always:
            send_user_notification(
                output.notify_text,
                title=_api_notification_title_status(result.host, output.title),
            )
    return results[-1]


if __name__ == "__main__":
    run_monitor()
