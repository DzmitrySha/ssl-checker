"""Точка входа проекта."""

import argparse
import sys
from pathlib import Path

from config.settings import LANGUAGE, SITE_PORT
from core.logger import logger
from core.batch_report import run_batch_report
from core.ssl_cert_monitor import run_monitor
from locales import _, init_translation, get_available_langs


class _CliHelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    """Подписи с дефолтами + epilog с переносами строк как в исходнике."""


def main() -> None:
    init_translation(LANGUAGE)

    if not Path(".env").is_file():
        logger.warning(_("env_file_not_found"))

    parser = argparse.ArgumentParser(
        description=_("cli_description"),
        formatter_class=_CliHelpFormatter,
        epilog=_("cli_epilog_examples"),
    )
    parser.add_argument(
        "--site",
        metavar="HOST_OR_URL",
        help=_("cli_arg_site_help"),
    )
    parser.add_argument("--port", type=int, default=SITE_PORT, help=_("cli_arg_port_help"))
    parser.add_argument("--json", action="store_true", dest="as_json", help=_("cli_arg_json_help"))
    parser.add_argument(
        "--notify-always",
        action="store_true",
        help=_("cli_arg_notify_always_help"),
    )
    parser.add_argument(
        "--lang",
        choices=get_available_langs(),
        help=_("cli_arg_lang_help"),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--batch",
        action="store_true",
        help=_("cli_arg_batch_help"),
    )
    mode.add_argument(
        "--schedule",
        action="store_true",
        help=_("cli_arg_schedule_help"),
    )
    args = parser.parse_args()

    init_translation(args.lang)

    if args.batch and args.site:
        parser.error(_("cli_error_batch_and_site"))
    if args.schedule and (args.site or args.as_json):
        parser.error(
            _("cli_error_schedule_with_site_or_json"),
        )
    if args.schedule and args.notify_always:
        parser.error(_("cli_error_schedule_with_notify_always"))

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