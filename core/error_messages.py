"""Единые тексты ошибок проверки TLS: пакетный отчёт, окна Windows, API-уведомления."""

from __future__ import annotations

from dataclasses import dataclass

from core.models import ErrorCode


@dataclass(frozen=True, slots=True)
class ErrorPresentation:
    """Короткая метка для сводки + заголовок и тело диалога (плейсхолдер {host})."""

    batch_label: str
    dialog_title: str
    dialog_body: str


_DEFAULT_UNKNOWN = ErrorPresentation(
    batch_label="неизвестная ошибка",
    dialog_title="Ошибка проверки",
    dialog_body="Проверка «{host}» завершилась с ошибкой. Подробности — в журнале приложения (папка logs).",
)

_ERROR_PRESENTATIONS: dict[ErrorCode, ErrorPresentation] = {
    ErrorCode.SSL_VERIFY_FAILED: ErrorPresentation(
        batch_label="ошибка проверки TLS",
        dialog_title="Ошибка проверки TLS",
        dialog_body=(
            "Не удалось установить доверенное соединение с «{host}» и прочитать сертификат.\n\n"
            "Проверьте настройку TLS_VERIFY: системные корни Windows, отключение проверки или путь к PEM-файлу "
            "корневого сертификата вашей организации. Файл корня не заменяет самоподписанный сертификат сайта — "
            "на сервере нужен сертификат, выданный доверенным центром сертификации."
        ),
    ),
    ErrorCode.TIMEOUT: ErrorPresentation(
        batch_label="таймаут",
        dialog_title="Нет ответа от сервера",
        dialog_body=(
            "Сервер «{host}» не ответил по TLS в отведённое время.\n\n"
            "Проверьте доступность узла, порт и сетевые ограничения."
        ),
    ),
    ErrorCode.NO_PEER_CERT: ErrorPresentation(
        batch_label="нет сертификата",
        dialog_title="Сертификат не получен",
        dialog_body="Узел «{host}» не прислал сертификат при TLS-рукопожатии. Проверьте порт и настройки сервера.",
    ),
    ErrorCode.CERT_PARSE_FAILED: ErrorPresentation(
        batch_label="ошибка разбора сертификата",
        dialog_title="Не удалось прочитать сертификат",
        dialog_body=(
            "Не удалось разобрать сертификат узла «{host}» и определить срок действия.\n\n"
            "Подробности — в журнале приложения (папка logs)."
        ),
    ),
    ErrorCode.CONNECTION_ERROR: ErrorPresentation(
        batch_label="ошибка подключения",
        dialog_title="Ошибка подключения",
        dialog_body="Не удалось подключиться к «{host}». Проверьте адрес, порт и сеть. Подробности — в журнале (logs).",
    ),
    ErrorCode.UNKNOWN_ERROR: ErrorPresentation(
        batch_label="неизвестная ошибка",
        dialog_title="Ошибка проверки",
        dialog_body="Проверка «{host}» завершилась с ошибкой. Подробности — в журнале приложения (папка logs).",
    ),
}


def get_error_presentation(code: ErrorCode | None) -> ErrorPresentation:
    if code is None:
        return _DEFAULT_UNKNOWN
    return _ERROR_PRESENTATIONS.get(
        code,
        ErrorPresentation(
            batch_label=code.value,
            dialog_title="Ошибка проверки",
            dialog_body="Проверка «{host}» завершилась с ошибкой (код: " + code.value + ").",
        ),
    )


def error_batch_label(code: ErrorCode | None) -> str:
    return get_error_presentation(code).batch_label


def build_error_dialog(code: ErrorCode, host: str) -> tuple[str, str]:
    p = get_error_presentation(code)
    return p.dialog_title, p.dialog_body.format(host=host)
