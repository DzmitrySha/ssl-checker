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
from core.status_policy import build_status_output, check_result_requires_remote_alert
from locales import _
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
        return _("log_tls_verify_false")
    if isinstance(verify, str):
        return _("log_tls_verify_cafile", cafile=verify)
    return _("log_tls_verify_true")


def _cert_datetime_display(dt: datetime) -> str:
    """Дата/время окончания (или начала) действия для отображения — без суффикса UTC."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _dt_utc_from_crypto(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _peer_summary_from_der(der: bytes) -> PeerCertSummary:
    if cryptography_x509 is None or cryptography_default_backend is None:
        raise RuntimeError(_("log_need_cryptography"))
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
    logger.info(_("log_check_started", host=host, port=port, caption=_verify_log_caption(verify)))

    def ok_pack(peer: PeerCertSummary, chain_trusted: bool) -> CheckResult:
        expiry_utc = peer.not_after_utc
        today = datetime.now(timezone.utc).date()
        end_d = expiry_utc.astimezone(timezone.utc).date()
        days = (end_d - today).days
        line = _cert_datetime_display(expiry_utc)
        chain_note = ""
        if not chain_trusted:
            from core.status_policy import CERT_DATE_CHAIN_NOTE
            line += CERT_DATE_CHAIN_NOTE
            chain_note = CERT_DATE_CHAIN_NOTE
        not_before_line = _cert_datetime_display(peer.not_before_utc)
        logger.info(
            _("log_cert_expiry", host=host, port=port, expiry=line, days=days),
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
            logger.info(_("log_tls_verify_cafile_explanation"))
        if TLS_READ_EXPIRY_ON_VERIFY_FAIL and verify is not False:
            logger.warning(_("log_tls_strict_failed", host=host, port=port, error=e))
            logger.info(_("log_tls_retry_no_verify"))
            try:
                return ok_pack(_read_peer_summary(host, port, _tls_context(False)), False)
            except (ssl.SSLError, OSError, TimeoutError, socket.timeout) as e2:
                logger.error(_("log_tls_retry_failed", host=host, port=port, error=e2))
            except (RuntimeError, ValueError) as e2:
                logger.error(
                    _("log_cert_parse_failed_crypto", host=host, port=port, error=e2),
                )
                return CheckResult(host, port, False, None, None, False, ErrorCode.CERT_PARSE_FAILED)
        else:
            logger.error(_("log_tls_error", host=host, port=port, error=e))
        logger.info(_("log_tls_verify_hint"))
        return CheckResult(host, port, False, None, None, False, ErrorCode.SSL_VERIFY_FAILED)
    except (TimeoutError, socket.timeout):
        logger.error(
            _("log_timeout", host=host, port=port, timeout=_TLS_TIMEOUT_SEC),
        )
        return CheckResult(host, port, False, None, None, False, ErrorCode.TIMEOUT)
    except NoPeerCertError:
        logger.error(_("log_no_peer_cert", host=host, port=port))
        return CheckResult(host, port, False, None, None, False, ErrorCode.NO_PEER_CERT)
    except OSError as e:
        logger.error(_("log_socket_error", host=host, port=port, error=e))
        return CheckResult(host, port, False, None, None, False, ErrorCode.CONNECTION_ERROR)
    except (RuntimeError, ValueError) as e:
        logger.error(_("log_cert_parse_failed", host=host, port=port, error=e))
        return CheckResult(host, port, False, None, None, False, ErrorCode.CERT_PARSE_FAILED)


def run_monitor(
    *,
    site: str | None = None,
    site_port: int = SITE_PORT,
    as_json: bool = False,
    force_notify_always: bool = False,
) -> CheckResult:
    from core.batch_report import format_batch_report

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
            send_user_notification(
                format_batch_report([result]),
                title=_("batch_report_title"),
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
        if check_result_requires_remote_alert(result):
            send_user_notification(
                format_batch_report([result]),
                title=_("batch_report_title"),
            )
        if output.kind is not AlertKind.NONE:
            show_window_alert(output.title, output.body, kind=output.kind)
        elif force_notify_always:
            send_user_notification(
                format_batch_report([result]),
                title=_("batch_report_title"),
            )
    return results[-1]


if __name__ == "__main__":
    run_monitor()