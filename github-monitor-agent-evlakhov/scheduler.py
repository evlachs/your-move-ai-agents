"""
scheduler.py — точка входа агента мониторинга GitHub
Запускает агента раз в день в 09:00 по московскому времени
"""

import logging
import signal
import sys
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# Настройка логирования — важно для отладки в Яндекс Клауд
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


def handle_shutdown(signum, frame):
    """Graceful shutdown при получении сигнала остановки (Ctrl+C, Docker stop)."""
    logger.info("Получен сигнал остановки. Завершаем планировщик...")
    scheduler.shutdown(wait=False)
    sys.exit(0)


if __name__ == "__main__":

    # Регистрируем обработчики сигналов для корректной остановки в Docker
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Создаём планировщик
    # BlockingScheduler — блокирует основной поток, идеально для контейнера
    scheduler = BlockingScheduler(timezone="Europe/Moscow")

    # Добавляем задачу: каждый день в 09:00 МСК
    scheduler.add_job(
        func=run_agent,
        trigger=CronTrigger(
            hour=9,
            minute=0,
            timezone="Europe/Moscow",
        ),
        id="github_monitor",
        name="Мониторинг GitHub репозитория",
        # Если контейнер был выключен в момент запуска —
        # запустить задачу сразу при старте (не ждать следующих 09:00)
        misfire_grace_time=3600,  # даём 1 час форс-мажора
        coalesce=True,            # если пропустили несколько запусков — запустить один раз
    )

    logger.info("Планировщик запущен. Агент будет работать каждый день в 09:00 МСК.")
    logger.info("Для немедленного запуска: python -c 'from scheduler import run_agent; run_agent()'")

    # Запускаем — блокирует выполнение до остановки
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Планировщик остановлен.")