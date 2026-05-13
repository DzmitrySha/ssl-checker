"""Ежедневный запуск пакетной проверки TLS (режим долгоживущего процесса / Docker)."""

from __future__ import annotations

import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from config.settings import (
    DAILY_BATCH_HOUR,
    DAILY_BATCH_MINUTE,
    RUN_BATCH_ON_START,
    SCHEDULER_TIMEZONE,
)
from core.batch_report import run_batch_report
from core.logger import logger


def _scheduled_batch() -> None:
    try:
        run_batch_report()
    except Exception:
        logger.exception("Ошибка при выполнении пакетной проверки по расписанию")


def run_daily_scheduler() -> None:
    """Блокирует поток: cron каждый день + опционально первая проверка при старте."""
    tz = SCHEDULER_TIMEZONE
    scheduler = BlockingScheduler(timezone=tz)

    def _shutdown(signum: int, _frame: object | None) -> None:
        logger.info("Сигнал {}, останавливаем планировщик...", signum)
        if scheduler.running:
            scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    scheduler.add_job(
        _scheduled_batch,
        "cron",
        hour=DAILY_BATCH_HOUR,
        minute=DAILY_BATCH_MINUTE,
        id="daily_batch",
        replace_existing=True,
    )
    logger.info(
        "Планировщик: каждый день в {:02d}:{:02d} ({})",
        DAILY_BATCH_HOUR,
        DAILY_BATCH_MINUTE,
        tz,
    )

    if RUN_BATCH_ON_START:
        logger.info("Пакетная проверка при старте (RUN_BATCH_ON_START=true)")
        _scheduled_batch()

    scheduler.start()
    sys.exit(0)
