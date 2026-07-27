"""
scheduler.py — планировщик агента мониторинга вакансий
Проверяет HH.ru раз в N часов.
"""

import logging
import signal
import sys
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

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
        trigger=IntervalTrigger(hours=config.check_interval_hours),
        id='vacancy_check',
        name='Проверка новых вакансий на HH.ru',
        misfire_grace_time=3600,
        coalesce=True,
    )

    logger.info(
        f'Планировщик запущен. Проверка HH.ru каждые {config.check_interval_hours} ч. '
        f'({config.timezone}).'
    )
    logger.info('Для немедленного запуска: python main.py --once')

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info('Планировщик остановлен.')


if __name__ == '__main__':
    start()
