"""Правила интерпретации результата проверки сертификата."""

from __future__ import annotations

from enum import Enum

from config.settings import CRITICAL_DAYS, WARN_DAYS
from core.models import AlertKind, CheckResult, StatusOutput

CERT_DATE_CHAIN_NOTE = " (цепочка доверия к издателю сертификата не проверялась)"


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
        lines.append(f"Издатель (кто выдал сертификат): {_friendly_cn(issuer)}")
    if subject:
        lines.append(f"Субъект (имя в сертификате): {_friendly_cn(subject)}")
    if not_before_line:
        lines.append(f"Начало действия: {not_before_line}")
    if not lines:
        return ""
    lines.append(f"Окончание действия: {end}")
    return "\n".join(lines)


def _chain_note_block() -> str:
    return (
        "\n\nПримечание: не прошла проверка **цепочки доверия** — программа не смогла связать сертификат сайта "
        "с известными в этой среде издателями (центрами сертификации). В браузере сайт тоже может не открываться.\n\n"
        "Что можно сделать: в параметре TLS_VERIFY указать **путь к файлу корневого сертификата вашей организации** "
        "(текстовый формат PEM); либо установить этот корневой сертификат в Windows в раздел "
        "«Доверенные корневые центры сертификации»; либо исправить неполную цепочку на самом сервере сайта."
    )


def _chain_footer_md(chain_ok: bool) -> str:
    if chain_ok:
        return ""
    return "\n\n_Срок взят из поля действия сертификата сайта (издатель не проверялся)._"


def _notify_ok_md(
    host: str,
    days_left: int,
    end: str,
    chain_ok: bool,
    issuer: str | None,
    subject: str | None,
    not_before_line: str | None,
) -> str:
    chain_txt = "подтверждена" if chain_ok else "не подтверждена"
    parts: list[str] = [
        "### Сертификат в порядке",
        "",
        f"**Домен:** `{host}`",
        f"**Осталось кал. дней:** `{days_left}`",
    ]
    if not_before_line:
        parts.append(f"**Начало действия:** `{not_before_line}`")
    parts.append(f"**Окончание действия:** `{end}`")
    parts.append(f"**Цепочка доверия:** {chain_txt}")
    if issuer:
        parts.append(f"**Издатель:** {_friendly_cn(issuer)}")
    if subject:
        parts.append(f"**Субъект:** {_friendly_cn(subject)}")
    return "\n".join(parts)


def _notify_expired_md(host: str, end: str, days_left: int, chain_ok: bool) -> str:
    if days_left < 0:
        conclusion = f"Просрочен на `{-days_left}` кал. дней"
        heading = "### Сертификат просрочен"
    else:
        conclusion = "Дата окончания — сегодня"
        heading = "### Срок действия истекает сегодня"
    parts = [
        heading,
        "",
        f"**Домен:** `{host}`",
        f"**Окончание действия:** `{end}`",
        f"**Заключение:** {conclusion}",
    ]
    return "\n".join(parts) + _chain_footer_md(chain_ok)


def _notify_critical_md(host: str, end: str, days_left: int, chain_ok: bool) -> str:
    parts = [
        "### Критическое предупреждение",
        "",
        f"**Домен:** `{host}`",
        f"**Окончание действия:** `{end}`",
        f"**Осталось кал. дней:** `{days_left}` (порог: < `{CRITICAL_DAYS}`)",
        "**Заключение:** запланировать замену сертификата.",
    ]
    return "\n".join(parts) + _chain_footer_md(chain_ok)


def _notify_warn_md(host: str, end: str, days_left: int, chain_ok: bool) -> str:
    parts = [
        "### Предупреждение",
        "",
        f"**Домен:** `{host}`",
        f"**Окончание действия:** `{end}`",
        f"**Осталось кал. дней:** `{days_left}` (порог: < `{WARN_DAYS}`)",
        "**Заключение:** подготовить обновление сертификата.",
    ]
    return "\n".join(parts) + _chain_footer_md(chain_ok)


def _notify_chain_md(host: str, end: str, days_left: int) -> str:
    return "\n".join(
        [
            "### Предупреждение (цепочка доверия)",
            "",
            f"**Домен:** `{host}`",
            f"**Окончание действия:** `{end}`",
            f"**Осталось кал. дней:** `{days_left}`",
            "",
            "_Издателя сертификата (центр сертификации) не удалось подтвердить из доверенного хранилища — "
            "в браузере сайт может не открываться._",
        ]
    )


def format_error_notification_markdown(*, title: str, host: str, body: str) -> str:
    one = body.replace("\n", " ").strip()
    return "\n".join(
        [
            "### Ошибка проверки TLS",
            "",
            f"**Домен:** `{host}`",
            f"**Тип:** {title}",
            f"**Детали:** {one}",
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
            title = "Сертификат просрочен"
            head = f"Сертификат для «{host}» просрочен на {-days_left} календарных дней."
        else:
            title = "Срок действия — сегодня"
            head = f"Сертификат для «{host}»: дата окончания по сертификату — сегодня. Запланируйте замену."
        body = f"{head}\n{cd}" if cd else f"{head}\nОкончание действия: {end}."
        ntxt = _notify_expired_md(host, end, days_left, chain_ok)
        return StatusOutput(title, body + note, ntxt, AlertKind.ERROR)

    if level is CheckOutcomeLevel.CRITICAL_WINDOW:
        title = "Критическое предупреждение"
        head = (
            f"Для «{host}» до окончания сертификата осталось дней: {days_left} "
            f"(меньше порога {CRITICAL_DAYS} календарных дней)."
        )
        body = f"{head}\n{cd}" if cd else f"{head}\nОкончание действия: {end}."
        ntxt = _notify_critical_md(host, end, days_left, chain_ok)
        return StatusOutput(title, body + note, ntxt, AlertKind.ERROR)

    if level is CheckOutcomeLevel.WARN_WINDOW:
        title = "Предупреждение"
        head = (
            f"Для «{host}» до окончания сертификата осталось дней: {days_left} "
            f"(меньше порога {WARN_DAYS} календарных дней)."
        )
        body = f"{head}\n{cd}" if cd else f"{head}\nОкончание действия: {end}."
        ntxt = _notify_warn_md(host, end, days_left, chain_ok)
        return StatusOutput(title, body + note, ntxt, AlertKind.WARNING)

    if level is CheckOutcomeLevel.CHAIN_ONLY_WARNING:
        title = "Проверка TLS"
        head = (
            f"По дате на сертификате для «{host}» до окончания ещё {days_left} календарных дней, "
            "но цепочка доверия к издателю не подтверждена."
        )
        body = f"{head}\n{cd}" if cd else f"{head}\nОкончание действия: {end}."
        ntxt = _notify_chain_md(host, end, days_left)
        return StatusOutput(title, body + note, ntxt, AlertKind.WARNING)

    head_ok = f"Сертификат для «{host}» в порядке. До окончания осталось календарных дней: {days_left}."
    console = f"{head_ok}\n{cd}" if cd else f"{head_ok}\nОкончание действия: {end}."
    notify = _notify_ok_md(host, days_left, end, chain_ok, issuer, subject, not_before_line)
    return StatusOutput("", console, notify, AlertKind.NONE)
