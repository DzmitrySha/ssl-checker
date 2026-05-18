"""Пакетная проверка списка хостов и один сводный отчёт во внешние каналы."""

from __future__ import annotations

from datetime import datetime, timezone

from config.settings import CRITICAL_DAYS, WARN_DAYS
from core.logger import logger
from core.error_messages import error_batch_label
from core.models import CheckResult
from core.site_list import load_site_entries
from core.ssl_cert_monitor import check_ssl_expiry
from core.status_policy import (
    CheckOutcomeLevel,
    _friendly_cn,
    _strip_chain_suffix,
    check_result_requires_attention,
    check_result_requires_remote_alert,
    classify_check_result,
)
from locales import _
from notifiers.notify import is_any_remote_send_configured, send_user_notification


def _batch_status_label_from_level(level: CheckOutcomeLevel, r: CheckResult) -> str:
    if level is CheckOutcomeLevel.OK:
        return _("batch_status_ok")
    if level is CheckOutcomeLevel.EXPIRED_OR_TODAY:
        dl = r.days_left
        if dl is not None and dl < 0:
            return _("batch_status_overdue")
        return _("batch_status_expires_today")
    if level is CheckOutcomeLevel.CRITICAL_WINDOW:
        return _("batch_status_critical")
    if level is CheckOutcomeLevel.WARN_WINDOW:
        return _("batch_status_warn")
    if level is CheckOutcomeLevel.CHAIN_ONLY_WARNING:
        return _("batch_status_chain_warning")
    return _("batch_status_error")


def _batch_status_emoji(level: CheckOutcomeLevel, r: CheckResult) -> str:
    if level is CheckOutcomeLevel.OK:
        return _("batch_status_emoji_ok")
    if level is CheckOutcomeLevel.EXPIRED_OR_TODAY:
        if r.days_left is not None and r.days_left < 0:
            return _("batch_status_emoji_overdue")
        return _("batch_status_emoji_today")
    if level is CheckOutcomeLevel.CRITICAL_WINDOW:
        return _("batch_status_emoji_critical")
    if level in (CheckOutcomeLevel.WARN_WINDOW, CheckOutcomeLevel.CHAIN_ONLY_WARNING):
        return _("batch_status_emoji_warn")
    return _("batch_status_emoji_error")


def _batch_status_md_for_error() -> str:
    return _("batch_status_md_error")


def _batch_status_md_for_ok(level: CheckOutcomeLevel, r: CheckResult) -> str:
    emoji = _batch_status_emoji(level, r)
    label = _batch_status_label_from_level(level, r)
    return f"**Status:** {emoji} {label}"


def _format_batch_entry_md(r: CheckResult) -> str:
    node = f"`{r.host}:{r.port}`"
    if not r.success:
        return "\n".join(
            [
                _("batch_entry_domain", node=node),
                _batch_status_md_for_error(),
                _("batch_entry_cause", label=error_batch_label(r.error_code)),
            ]
        )
    level = classify_check_result(r)
    days = r.days_left if r.days_left is not None else "?"
    end = _strip_chain_suffix((r.not_after_line or "").replace("\n", " "))
    chain_txt = _("chain_trusted") if r.chain_ok else _("chain_untrusted")
    parts: list[str] = [
        _("batch_entry_domain", node=node),
        _batch_status_md_for_ok(level, r),
        _("batch_entry_days_left", days=days),
    ]
    if r.not_before_line:
        parts.append(_("batch_entry_not_before", date=r.not_before_line))
    parts.append(_("batch_entry_not_after", date=end))
    parts.append(_("batch_entry_chain", chain=chain_txt))
    if r.issuer:
        parts.append(_("batch_entry_issuer", issuer=_friendly_cn(r.issuer)))
    if r.subject:
        parts.append(_("batch_entry_subject", subject=_friendly_cn(r.subject)))
    return "\n".join(parts)


def format_batch_report(results: list[CheckResult]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    green_n = sum(1 for r in results if classify_check_result(r) is CheckOutcomeLevel.OK)
    attention_n = len(results) - green_n
    header = "\n".join(
        [
            _("batch_report_time", time=now),
            _("batch_report_total", count=len(results)),
            _("batch_report_ok_count", count=green_n),
            _("batch_report_attention", count=attention_n),
        ]
    )
    blocks = [_format_batch_entry_md(r) for r in results]
    if not blocks:
        return header
    sep = "\n\n---\n\n"
    return header + sep + sep.join(blocks)


def run_batch_report(*, force_remote_notification: bool = False) -> int:
    entries = load_site_entries()
    logger.info(_("batch_started", count=len(entries)))
    results: list[CheckResult] = []
    for host, port in entries:
        results.append(check_ssl_expiry(host, site_port=port))

    text = format_batch_report(results)
    logger.info("\n{}\n", text)

    if is_any_remote_send_configured():
        need_alert = any(check_result_requires_remote_alert(r) for r in results)
        if force_remote_notification or need_alert:
            send_user_notification(text, title=_("batch_report_title"))
        elif any(
            classify_check_result(r) is CheckOutcomeLevel.CHAIN_ONLY_WARNING for r in results
        ):
            logger.info(_("batch_skip_remote_chain_only"))
        else:
            logger.info(
                _("batch_all_ok", warn=WARN_DAYS, critical=CRITICAL_DAYS),
            )
    else:
        logger.info(_("batch_notifications_off"))

    return 1 if any(check_result_requires_attention(r) for r in results) else 0