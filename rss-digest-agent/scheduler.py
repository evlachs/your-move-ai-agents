"""
scheduler.py — планировщик агента RSS-дайджеста
Запускает агента один раз в день в заданное время.
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

    scheduler = BlockingScheduler(timezone=config.timezone)

    def handle_shutdown(signum, frame):
        """Graceful shutdown при получении сигнала остановки (Ctrl+C, Docker stop)."""
        logger.info('Получен сигнал остановки. Завершаем планировщик...')
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    scheduler.add_job(
        func=run_agent,
        trigger=CronTrigger(
            hour=config.digest_hour,
            minute=config.digest_minute,
            timezone=config.timezone,
        ),
        id='rss_digest',
        name='Ежедневный RSS-дайджест',
        misfire_grace_time=3600,
        coalesce=True,
    )

    logger.info(
        f'Планировщик запущен. Дайджест в '
        f'{config.digest_hour:02d}:{config.digest_minute:02d} ({config.timezone}).'
    )
    logger.info('Для немедленного запуска: python main.py --once')

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info('Планировщик остановлен.')


if __name__ == '__main__':
    start()
