"""
core.py — главная логика агента
Цикл: observe → plan → act (статистика + анализ) → act (отправка) → observe
"""

import logging
from datetime import datetime, timedelta, timezone

from configs.config import load_config
from agent.memory import AgentMemory
from agent.tools import LogFetcherTool, YandexGPTTool, aggregate_logs
from agent.notifier import EmailNotifier

logger = logging.getLogger(__name__)


def run():
    """
    Точка входа агента — вызывается из main.py/scheduler.py раз в час.

    Цикл:
      1. observe — читаем записи логов за период с прошлой проверки
      2. plan    — если записей нет, всё равно сдвигаем границу и выходим
      3. act     — считаем статистику по уровням и анализируем ошибки через YandexGPT
      4. act     — генерируем тему дайджеста
      5. act     — отправляем дайджест на email
      6. observe — запоминаем границу 'until' (только после успешной отправки)
    """
    config = load_config()

    memory   = AgentMemory(config.db_path)
    fetcher  = LogFetcherTool(config)
    gpt      = YandexGPTTool(config)
    notifier = EmailNotifier(config)

    log_group_id = config.log_group_id
    until = datetime.now(timezone.utc).isoformat()
    since = memory.get_last_checked(log_group_id) or (
        datetime.now(timezone.utc) - timedelta(hours=config.check_interval_hours)
    ).isoformat()

    logger.info(f'Агент запущен. Лог-группа: {log_group_id}, период: {since} → {until}')

    # ── Шаг 1: observe ──────────────────────────────────────────────

    entries = fetcher.fetch_entries(since, until)

    # ── Шаг 2: plan ─────────────────────────────────────────────────

    if not entries:
        logger.info('Новых записей нет — агент завершает работу.')
        memory.set_last_checked(log_group_id, until)
        return

    # ── Шаг 3: act — статистика и анализ ─────────────────────────────

    level_counts, error_samples = aggregate_logs(entries)
    logger.info(f'Статистика по уровням: {dict(level_counts)}')

    analysis = gpt.analyze_logs(level_counts, error_samples)

    # ── Шаг 4: act — тема дайджеста ───────────────────────────────────

    subject_line = gpt.generate_digest_subject(level_counts)

    # ── Шаг 5: act — отправка ──────────────────────────────────────────

    sent = notifier.send_digest(log_group_id, level_counts, error_samples, analysis, subject_line)

    # ── Шаг 6: observe — запись в память ────────────────────────────
    # Важно: запоминаем ТОЛЬКО после успешной отправки.
    # Если письмо не ушло — при следующем запуске повторим то же окно.

    if sent:
        memory.set_last_checked(log_group_id, until)
        logger.info(f'Готово. Обработано записей: {len(entries)}')
    else:
        logger.warning(
            'Дайджест не отправлен — память не обновлена. '
            'При следующем запуске попробуем снова.'
        )
