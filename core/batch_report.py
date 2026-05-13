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
    check_result_requires_remote_alert,
    classify_check_result,
)
from notifiers.notify import is_any_remote_send_configured, send_user_notification


def _batch_status_label_from_level(level: CheckOutcomeLevel, r: CheckResult) -> str:
    """Краткий текст статуса (без эмодзи)."""
    if level is CheckOutcomeLevel.OK:
        return "OK"
    if level is CheckOutcomeLevel.EXPIRED_OR_TODAY:
        dl = r.days_left
        if dl is not None and dl < 0:
            return "просрочен"
        return "окончание сегодня"
    if level is CheckOutcomeLevel.CRITICAL_WINDOW:
        return "критический срок"
    if level is CheckOutcomeLevel.WARN_WINDOW:
        return "предупреждение по сроку"
    if level is CheckOutcomeLevel.CHAIN_ONLY_WARNING:
        return "цепочка доверия не подтверждена"
    return "ошибка проверки"


def _batch_status_emoji(level: CheckOutcomeLevel, r: CheckResult) -> str:
    """Цветной индикатор в клиентах Mattermost (эмодзи; HTML в теле недоступен)."""
    if level is CheckOutcomeLevel.OK:
        return "🟢"
    if level is CheckOutcomeLevel.EXPIRED_OR_TODAY:
        if r.days_left is not None and r.days_left < 0:
            return "🔴"
        return "🟠"
    if level is CheckOutcomeLevel.CRITICAL_WINDOW:
        return "🟠"
    if level in (CheckOutcomeLevel.WARN_WINDOW, CheckOutcomeLevel.CHAIN_ONLY_WARNING):
        return "🟡"
    return "🔴"


def _batch_status_md_for_error() -> str:
    return "**Статус:** 🔴 ошибка"


def _batch_status_md_for_ok(level: CheckOutcomeLevel, r: CheckResult) -> str:
    emoji = _batch_status_emoji(level, r)
    label = _batch_status_label_from_level(level, r)
    return f"**Статус:** {emoji} {label}"


def _format_batch_entry_md(r: CheckResult) -> str:
    node = f"`{r.host}:{r.port}`"
    if not r.success:
        return "\n".join(
            [
                f"**Домен:** {node}",
                _batch_status_md_for_error(),
                f"**Причина:** {error_batch_label(r.error_code)}",
            ]
        )
    level = classify_check_result(r)
    days = r.days_left if r.days_left is not None else "?"
    end = _strip_chain_suffix((r.not_after_line or "").replace("\n", " "))
    chain_txt = "подтверждена" if r.chain_ok else "не подтверждена"
    parts: list[str] = [
        f"**Домен:** {node}",
        _batch_status_md_for_ok(level, r),
        f"**Осталось кал. дней:** `{days}`",
    ]
    if r.not_before_line:
        parts.append(f"**Начало действия:** `{r.not_before_line}`")
    parts.append(f"**Окончание действия:** `{end}`")
    parts.append(f"**Цепочка доверия:** {chain_txt}")
    if r.issuer:
        parts.append(f"**Издатель:** {_friendly_cn(r.issuer)}")
    if r.subject:
        parts.append(f"**Субъект:** {_friendly_cn(r.subject)}")
    return "\n".join(parts)


def format_batch_report(results: list[CheckResult]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    green_n = sum(1 for r in results if classify_check_result(r) is CheckOutcomeLevel.OK)
    attention_n = len(results) - green_n
    # Заголовок «Отчёт TLS…» передаётся отдельным полем title в API — не дублировать ### в тексте.
    header = "\n".join(
        [
            f"**Время:** `{now}`",
            f"**Проверено доменов:** `{len(results)}`",
            f"**Без замечаний (срок и цепочка):** `{green_n}`",
            f"**Требуют внимания:** `{attention_n}`",
        ]
    )
    blocks = [_format_batch_entry_md(r) for r in results]
    if not blocks:
        return header
    sep = "\n\n---\n\n"
    return header + sep + sep.join(blocks)


def run_batch_report(*, force_remote_notification: bool = False) -> int:
    """Проверяет все узлы из списка, печатает отчёт в консоль, при необходимости шлёт уведомление в API/Mattermost.

    По умолчанию удалённое уведомление отправляется только если есть повод: ошибка проверки, просрочка,
    срок < WARN_DAYS / < CRITICAL_DAYS или неподтверждённая цепочка (см. check_result_requires_remote_alert).

    С force_remote_notification=True отчёт уходит всегда (например отладка флага --notify-always в CLI).
    """
    entries = load_site_entries()
    logger.info("Пакетная проверка, доменов: {}", len(entries))
    results: list[CheckResult] = []
    for host, port in entries:
        results.append(check_ssl_expiry(host, site_port=port))

    text = format_batch_report(results)
    logger.info("\n{}\n", text)

    if is_any_remote_send_configured():
        need_alert = any(check_result_requires_remote_alert(r) for r in results)
        if not force_remote_notification and not need_alert:
            logger.info(
                "Все домены в норме (пороги WARN_DAYS={}, CRITICAL_DAYS={}) — удалённое уведомление не отправляется.",
                WARN_DAYS,
                CRITICAL_DAYS,
            )
        else:
            send_user_notification(text, title="Отчёт TLS (срок сертификатов)")
    else:
        logger.info(
            "Уведомления выключены или не настроены "
            "(SEND_NOTIFICATIONS и полный набор полей в .env); отчёт только выше."
        )

    return 1 if any(check_result_requires_remote_alert(r) for r in results) else 0
