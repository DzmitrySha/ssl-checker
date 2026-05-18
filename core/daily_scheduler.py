"""Ежедневный запуск пакетной проверки TLS (режим долгоживущего процесса / Docker)."""

from __future__ import annotations

import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from config.settings import DAILY_BATCH_HOURS, RUN_BATCH_ON_START, SCHEDULER_TIMEZONE
from core.batch_report import run_batch_report
from core.logger import logger
from locales import _


def _scheduled_batch() -> None:
    try:
        run_batch_report()
    except Exception:
        logger.exception(_("scheduler_batch_error"))


def run_daily_scheduler() -> None:
    """Блокирует поток: cron каждый день + опционально первая проверка при старте."""
    tz = SCHEDULER_TIMEZONE
    scheduler = BlockingScheduler(timezone=tz)

    def _shutdown(signum: int, _frame: object | None) -> None:
        logger.info(_("scheduler_shutdown", signum=signum))
        if scheduler.running:
            scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    hours_label = ", ".join(f"{h}:00" for h in DAILY_BATCH_HOURS)
    cron_hours = ",".join(str(h) for h in DAILY_BATCH_HOURS)
    scheduler.add_job(
        _scheduled_batch,
        "cron",
        hour=cron_hours,
        minute="0",
        id="daily_batch",
        replace_existing=True,
    )
    logger.info(_("scheduler_start", hours=hours_label, tz=tz))

    if RUN_BATCH_ON_START:
        logger.info(_("scheduler_batch_on_start"))
        _scheduled_batch()

    scheduler.start()
    sys.exit(0)