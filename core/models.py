"""Общие модели данных проекта."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class ErrorCode(str, Enum):
    SSL_VERIFY_FAILED = "ssl_verify_failed"
    TIMEOUT = "timeout"
    NO_PEER_CERT = "no_peer_cert"
    CERT_PARSE_FAILED = "cert_parse_failed"
    CONNECTION_ERROR = "connection_error"
    UNKNOWN_ERROR = "unknown_error"


class AlertKind(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    NONE = "none"


@dataclass
class CheckResult:
    host: str
    port: int
    success: bool
    days_left: int | None
    not_after_line: str | None
    chain_ok: bool
    error_code: ErrorCode | None
    subject: str | None = None
    issuer: str | None = None
    not_before_line: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class StatusOutput:
    title: str
    body: str
    notify_text: str
    kind: AlertKind
