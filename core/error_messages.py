"""Единые тексты ошибок проверки TLS: пакетный отчёт, окна Windows, API-уведомления."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.models import ErrorCode
from locales import _


@dataclass(frozen=True, slots=True)
class ErrorPresentation:
    batch_label_key: str
    dialog_title_key: str
    dialog_body_key: str


def _ep(
    batch_label_key: str,
    dialog_title_key: str,
    dialog_body_key: str,
) -> ErrorPresentation:
    return ErrorPresentation(batch_label_key, dialog_title_key, dialog_body_key)


_UNKNOWN_KEYS = ErrorPresentation(
    batch_label_key="error_batch_unknown",
    dialog_title_key="error_dialog_title_unknown",
    dialog_body_key="error_dialog_body_unknown",
)

_ERROR_PRESENTATIONS: dict[ErrorCode, ErrorPresentation] = {
    ErrorCode.SSL_VERIFY_FAILED: _ep(
        "error_batch_ssl_verify",
        "error_dialog_title_ssl_verify",
        "error_dialog_body_ssl_verify",
    ),
    ErrorCode.TIMEOUT: _ep(
        "error_batch_timeout",
        "error_dialog_title_timeout",
        "error_dialog_body_timeout",
    ),
    ErrorCode.NO_PEER_CERT: _ep(
        "error_batch_no_peer_cert",
        "error_dialog_title_no_peer_cert",
        "error_dialog_body_no_peer_cert",
    ),
    ErrorCode.CERT_PARSE_FAILED: _ep(
        "error_batch_cert_parse_failed",
        "error_dialog_title_cert_parse_failed",
        "error_dialog_body_cert_parse_failed",
    ),
    ErrorCode.CONNECTION_ERROR: _ep(
        "error_batch_connection_error",
        "error_dialog_title_connection_error",
        "error_dialog_body_connection_error",
    ),
    ErrorCode.UNKNOWN_ERROR: _UNKNOWN_KEYS,
}


def get_error_presentation(code: ErrorCode | None) -> ErrorPresentation:
    if code is None:
        return _UNKNOWN_KEYS
    if code in _ERROR_PRESENTATIONS:
        return _ERROR_PRESENTATIONS[code]
    return ErrorPresentation(
        batch_label_key=code.value,
        dialog_title_key="error_dialog_title_unknown",
        dialog_body_key="error_dialog_body_unknown_code",
    )


def error_batch_label(code: ErrorCode | None) -> str:
    ep = get_error_presentation(code)
    return _(ep.batch_label_key)


def build_error_dialog(code: ErrorCode, host: str) -> tuple[str, str]:
    ep = get_error_presentation(code)
    body_key = ep.dialog_body_key
    if body_key == "error_dialog_body_unknown_code":
        body = _(body_key, code=code.value)
    else:
        body = _(body_key, host=host)
    return _(ep.dialog_title_key), body