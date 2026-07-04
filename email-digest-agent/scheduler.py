"""
scheduler.py — планировщик агента почтовых дайджестов
Запускает агента ДВА раза в день: в обед и в конце рабочего дня.
"""

import logging
import signal
import sys
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from configs.config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_lunch_digest():
    _run_agent('Обеденный дайджест')


def run_evening_digest():
    _run_agent('Вечерний дайджест')


def _run_agent(period_label: str):
    """Запускается по расписанию — вызывает основной цикл агента."""
    try:
        from agent.core import run
        run(period_label)
    except Exception as e:
        logger.error(f'Ошибка во время работы агента: {e}', exc_info=True)


def start():
    """Настраивает и запускает планировщик. Блокирует основной поток."""
    config = load_config()

    def handle_shutdown(signum, frame):
        """Graceful shutdown при получении сигнала остановки (Ctrl+C, Docker stop)."""
        logger.info("Получен сигнал остановки. Завершаем планировщик...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # BlockingScheduler — блокирует основной поток, идеально для контейнера
    scheduler = BlockingScheduler(timezone=config.timezone)

    scheduler.add_job(
        func=run_lunch_digest,
        trigger=CronTrigger(
            hour=config.lunch_hour,
            minute=config.lunch_minute,
            timezone=config.timezone,
        ),
        id="lunch_digest",
        name="Обеденный дайджест почты",
        misfire_grace_time=3600,
        coalesce=True,
    )

    scheduler.add_job(
        func=run_evening_digest,
        trigger=CronTrigger(
            hour=config.evening_hour,
            minute=config.evening_minute,
            timezone=config.timezone,
        ),
        id="evening_digest",
        name="Вечерний дайджест почты",
        misfire_grace_time=3600,
        coalesce=True,
    )

    logger.info(
        f"Планировщик запущен. Дайджесты: "
        f"{config.lunch_hour:02d}:{config.lunch_minute:02d} и "
        f"{config.evening_hour:02d}:{config.evening_minute:02d} ({config.timezone})."
    )
    logger.info("Для немедленного запуска: python main.py --once")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Планировщик остановлен.")


if __name__ == "__main__":
    start()
