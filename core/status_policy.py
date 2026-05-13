"""Правила интерпретации результата проверки сертификата."""

from __future__ import annotations

from enum import Enum

from config.settings import CRITICAL_DAYS, WARN_DAYS
from core.models import AlertKind, CheckResult, StatusOutput
from locales import _

CERT_DATE_CHAIN_NOTE = _("chain_note_suffix")


class CheckOutcomeLevel(str, Enum):
    """Уровень исхода успешной проверки или факт сбоя (для алертов и удалённых уведомлений)."""

    OK = "ok"
    EXPIRED_OR_TODAY = "expired_or_today"
    CRITICAL_WINDOW = "critical"
    WARN_WINDOW = "warn"
    CHAIN_ONLY_WARNING = "chain"
    CHECK_FAILED = "failed"


def _classify_success_days_chain(days_left: int, chain_ok: bool) -> CheckOutcomeLevel:
    if days_left <= 0:
        return CheckOutcomeLevel.EXPIRED_OR_TODAY
    if days_left < CRITICAL_DAYS:
        return CheckOutcomeLevel.CRITICAL_WINDOW
    if days_left < WARN_DAYS:
        return CheckOutcomeLevel.WARN_WINDOW
    if not chain_ok:
        return CheckOutcomeLevel.CHAIN_ONLY_WARNING
    return CheckOutcomeLevel.OK


def classify_check_result(r: CheckResult) -> CheckOutcomeLevel:
    if not r.success or r.days_left is None:
        return CheckOutcomeLevel.CHECK_FAILED
    return _classify_success_days_chain(r.days_left, r.chain_ok)


def check_result_requires_remote_alert(r: CheckResult) -> bool:
    """Нужно ли слать удалённое уведомление по узлу: те же пороги, что в build_status_output."""
    return classify_check_result(r) is not CheckOutcomeLevel.OK


def _strip_chain_suffix(s: str) -> str:
    return s[: -len(CERT_DATE_CHAIN_NOTE)] if s.endswith(CERT_DATE_CHAIN_NOTE) else s


def _friendly_cn(rfc4514: str, *, max_len: int = 160) -> str:
    """Читаемое имя из DN: значение CN= или усечённая строка."""
    for segment in rfc4514.split(","):
        s = segment.strip()
        if len(s) >= 3 and s[:3].upper() == "CN=":
            v = s[3:].strip()
            return v if v else rfc4514
    return rfc4514 if len(rfc4514) <= max_len else rfc4514[: max_len - 1] + "…"


def _cert_details_block(
    issuer: str | None,
    subject: str | None,
    not_before_line: str | None,
    end: str,
) -> str:
    lines: list[str] = []
    if issuer:
        lines.append(_("cert_issuer_label", issuer=_friendly_cn(issuer)))
    if subject:
        lines.append(_("cert_subject_label", subject=_friendly_cn(subject)))
    if not_before_line:
        lines.append(_("cert_not_before_label", date=not_before_line))
    if not lines:
        return ""
    lines.append(_("cert_not_after_label", date=end))
    return "\n".join(lines)


def _chain_note_block() -> str:
    return _("chain_note_block")


def _chain_footer_md(chain_ok: bool) -> str:
    if chain_ok:
        return ""
    return _("chain_footer_untrusted")


def _notify_ok_md(
    host: str,
    days_left: int,
    end: str,
    chain_ok: bool,
    issuer: str | None,
    subject: str | None,
    not_before_line: str | None,
) -> str:
    chain_txt = _("chain_trusted") if chain_ok else _("chain_untrusted")
    parts: list[str] = [
        f"### {_('notify_ok_title')}",
        "",
        _(f"notify_ok_domain", host=host),
        _(f"notify_ok_days_left", days=days_left),
    ]
    if not_before_line:
        parts.append(_("notify_ok_not_before", date=not_before_line))
    parts.append(_("notify_ok_not_after", date=end))
    parts.append(_("notify_ok_chain", chain=chain_txt))
    if issuer:
        parts.append(_("notify_ok_issuer", issuer=_friendly_cn(issuer)))
    if subject:
        parts.append(_("notify_ok_subject", subject=_friendly_cn(subject)))
    return "\n".join(parts)


def _notify_expired_md(host: str, end: str, days_left: int, chain_ok: bool) -> str:
    if days_left < 0:
        conclusion_key = "notify_expired_conclusion_overdue"
        conclusion_val = -days_left
        heading_key = "notify_expired_heading"
    else:
        conclusion_key = "notify_expired_conclusion_today"
        conclusion_val = None
        heading_key = "notify_expired_heading_today"
    parts = [
        _(heading_key),
        "",
        _("notify_ok_domain", host=host),
        _("notify_ok_not_after", date=end),
        _(conclusion_key, days=conclusion_val) if conclusion_val is not None else f"**Conclusion:** {_(conclusion_key)}",
    ]
    return "\n".join(parts) + _chain_footer_md(chain_ok)


def _notify_critical_md(host: str, end: str, days_left: int, chain_ok: bool) -> str:
    parts = [
        f"### {_('notify_critical_heading')}",
        "",
        _(f"notify_ok_domain", host=host),
        _(f"notify_ok_not_after", date=end),
        _("notify_critical_days_left", days=days_left, threshold=CRITICAL_DAYS),
        _("notify_critical_conclusion"),
    ]
    return "\n".join(parts) + _chain_footer_md(chain_ok)


def _notify_warn_md(host: str, end: str, days_left: int, chain_ok: bool) -> str:
    parts = [
        f"### {_('notify_warn_heading')}",
        "",
        _(f"notify_ok_domain", host=host),
        _(f"notify_ok_not_after", date=end),
        _("notify_warn_days_left", days=days_left, threshold=WARN_DAYS),
        _("notify_warn_conclusion"),
    ]
    return "\n".join(parts) + _chain_footer_md(chain_ok)


def _notify_chain_md(host: str, end: str, days_left: int) -> str:
    return "\n".join(
        [
            f"### {_('notify_chain_heading')}",
            "",
            _(f"notify_ok_domain", host=host),
            _(f"notify_ok_not_after", date=end),
            _(f"notify_ok_days_left", days=days_left),
            "",
            _("notify_chain_note"),
        ]
    )


def format_error_notification_markdown(*, title: str, host: str, body: str) -> str:
    one = body.replace("\n", " ").strip()
    return "\n".join(
        [
            f"### {_('error_notification_title')}",
            "",
            _(f"error_notification_domain", host=host),
            _(f"error_notification_type", title=title),
            _(f"error_notification_details", body=one),
        ]
    )


def build_status_output(
    host: str,
    days_left: int,
    not_after_line: str,
    chain_ok: bool,
    *,
    subject: str | None = None,
    issuer: str | None = None,
    not_before_line: str | None = None,
) -> StatusOutput:
    end = _strip_chain_suffix(not_after_line)
    note = _chain_note_block() if not chain_ok else ""
    cd = _cert_details_block(issuer, subject, not_before_line, end)
    level = _classify_success_days_chain(days_left, chain_ok)

    if level is CheckOutcomeLevel.EXPIRED_OR_TODAY:
        if days_left < 0:
            title = _("status_expired_title")
            head = _("status_expired_head_overdue", host=host, days=-days_left)
        else:
            title = _("status_expired_title")
            head = _("status_expired_head_today", host=host)
        body = f"{head}\n{cd}" if cd else f"{head}\n{_('status_expired_body_tail', end=end)}"
        ntxt = _notify_expired_md(host, end, days_left, chain_ok)
        return StatusOutput(title, body + note, ntxt, AlertKind.ERROR)

    if level is CheckOutcomeLevel.CRITICAL_WINDOW:
        title = _("status_critical_title")
        head = _("status_critical_head", host=host, days=days_left, threshold=CRITICAL_DAYS)
        body = f"{head}\n{cd}" if cd else f"{head}\n{_('status_expired_body_tail', end=end)}"
        ntxt = _notify_critical_md(host, end, days_left, chain_ok)
        return StatusOutput(title, body + note, ntxt, AlertKind.ERROR)

    if level is CheckOutcomeLevel.WARN_WINDOW:
        title = _("status_warn_title")
        head = _("status_warn_head", host=host, days=days_left, threshold=WARN_DAYS)
        body = f"{head}\n{cd}" if cd else f"{head}\n{_('status_expired_body_tail', end=end)}"
        ntxt = _notify_warn_md(host, end, days_left, chain_ok)
        return StatusOutput(title, body + note, ntxt, AlertKind.WARNING)

    if level is CheckOutcomeLevel.CHAIN_ONLY_WARNING:
        title = _("status_chain_title")
        head = _("status_chain_head", host=host, days=days_left)
        body = f"{head}\n{cd}" if cd else f"{head}\n{_('status_expired_body_tail', end=end)}"
        ntxt = _notify_chain_md(host, end, days_left)
        return StatusOutput(title, body + note, ntxt, AlertKind.WARNING)

    head_ok = _("status_ok_head", host=host, days=days_left)
    console = f"{head_ok}\n{cd}" if cd else f"{head_ok}\n{_('status_expired_body_tail', end=end)}."
    notify = _notify_ok_md(host, days_left, end, chain_ok, issuer, subject, not_before_line)
    return StatusOutput("", console, notify, AlertKind.NONE)