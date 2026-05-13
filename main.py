"""Точка входа проекта."""

import argparse
import sys
from pathlib import Path

from config.settings import SITE_PORT
from core.logger import logger
from core.batch_report import run_batch_report
from core.ssl_cert_monitor import run_monitor


class _CliHelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    """Подписи с дефолтами + epilog с переносами строк как в исходнике."""


def main() -> None:
    if not Path(".env").is_file():
        logger.warning("Файл .env не найден. Скопируйте шаблон: .env.example -> .env")

    parser = argparse.ArgumentParser(
        description=(
            "Мониторинг TLS-сертификата. "
            "Режим по умолчанию — разовая проверка из CLI: один узел (--site) или весь список из .env, "
            "если --site не задан."
        ),
        formatter_class=_CliHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  %(prog)s --help\n"
            "  %(prog)s --site example.com\n"
            "  %(prog)s --site https://example.com:8443 --json\n"
            "  %(prog)s --port 443 --json\n"
            "  %(prog)s --batch\n"
            "  %(prog)s --batch --notify-always\n"
            "  %(prog)s --schedule"
        ),
    )
    parser.add_argument(
        "--site",
        metavar="HOST_OR_URL",
        help="Один хост или URL; без этого флага берётся список SITES_TO_CHECK / SITES_FILE из .env",
    )
    parser.add_argument("--port", type=int, default=SITE_PORT, help="Порт TLS, если в --site нет порта")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Результат в JSON (stdout)")
    parser.add_argument(
        "--notify-always",
        action="store_true",
        help=(
            "Принудительно отправить уведомление в API/Mattermost даже если всё в порядке "
            "(отладка). С --batch — полный отчёт; при разовой проверке — сообщение и при «зелёном» сертификате."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--batch",
        action="store_true",
        help="Один раз: все узлы из списка и один сводный отчёт (уведомления по настройкам .env)",
    )
    mode.add_argument(
        "--schedule",
        action="store_true",
        help="Долгоживущий процесс: ежедневная пакетная проверка по времени из .env (удобно в Docker)",
    )
    args = parser.parse_args()

    if args.batch and args.site:
        parser.error("сочетание --batch и --site не поддерживается: для одного узла укажите только --site")
    if args.schedule and (args.site or args.as_json):
        parser.error(
            "режим --schedule только для фонового расписания; "
            f"ручная проверка — без --schedule (см. {parser.prog} --help)"
        )
    if args.schedule and args.notify_always:
        parser.error("флаг --notify-always не используется в режиме --schedule")

    if args.batch:
        code = run_batch_report(force_remote_notification=args.notify_always)
        sys.exit(code)

    if args.schedule:
        from core.daily_scheduler import run_daily_scheduler

        run_daily_scheduler()
        return

    run_monitor(
        site=args.site,
        site_port=args.port,
        as_json=args.as_json,
        force_notify_always=args.notify_always,
    )


if __name__ == "__main__":
    main()
