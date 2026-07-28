"""
scheduler.py — планировщик SMM-агента
Запускает агента раз в день в заданное время (по умолчанию 09:00 МСК) —
готовит черновик поста на завтра, оставляя время на проверку в VK.
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


def run_agent():
    """Запускается по расписанию — вызывает основной цикл агента."""
    try:
        from agent.core import run
        run()
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
        func=run_agent,
        trigger=CronTrigger(
            hour=config.schedule_hour,
            minute=config.schedule_minute,
            timezone=config.timezone,
        ),
        id="smm_agent",
        name="Генерация черновика поста для VK",
        # Если контейнер был выключен в момент запуска —
        # запустить задачу сразу при старте (не ждать следующего дня)
        misfire_grace_time=3600,
        coalesce=True,
    )

    logger.info(
        f"Планировщик запущен. Агент будет работать каждый день "
        f"в {config.schedule_hour:02d}:{config.schedule_minute:02d} ({config.timezone})."
    )
    logger.info("Для немедленного запуска: python main.py --once")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Планировщик остановлен.")


if __name__ == "__main__":
    start()
