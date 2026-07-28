"""
core.py — главная логика агента
Цикл: observe → plan → act (суммаризация) → act (отправка) → observe
"""

import logging

from configs.config import load_config
from agent.memory import AgentMemory
from agent.tools import RSSFetcherTool, YandexGPTTool
from agent.notifier import EmailNotifier

logger = logging.getLogger(__name__)


def run():
    """
    Точка входа агента — вызывается из main.py/scheduler.py раз в день.

    Цикл:
      1. observe — читаем все RSS-ленты, получаем список записей
      2. plan    — фильтруем уже виденные по ID из SQLite; если новых нет — выходим
      3. act     — суммаризируем каждую новую запись через YandexGPT
      4. act     — отправляем дайджест на email
      5. observe — помечаем ВСЕ новые записи как виденные (независимо от результата GPT),
                   но только после успешной отправки
    """
    config = load_config()

    memory = AgentMemory(config.db_path)
    fetcher = RSSFetcherTool(config)
    gpt = YandexGPTTool(config)
    notifier = EmailNotifier(config)

    # ── Шаг 1: observe ──────────────────────────────────────────────

    all_entries = fetcher.fetch_all()
    seen_ids = memory.get_seen_ids()

    # ── Шаг 2: plan ─────────────────────────────────────────────────

    new_entries = [e for e in all_entries if e.id not in seen_ids]

    if not new_entries:
        logger.info('Новых записей нет — агент завершает работу.')
        return

    logger.info(f'Новых записей: {len(new_entries)}. Начинаем суммаризацию...')

    # ── Шаг 3: act — суммаризация ───────────────────────────────────

    for entry in new_entries:
        logger.info(f'Суммаризируем: [{entry.feed_title}] {entry.title}')
        entry.digest = gpt.summarize(entry)

    # ── Шаг 4: act — отправка ───────────────────────────────────────

    sent = notifier.send_digest(new_entries)

    # ── Шаг 5: observe — запись в память ────────────────────────────
    # Помечаем все новые записи — даже если GPT не дал резюме для части из них.
    # Цель памяти — не показывать одно и то же дважды.
    # Если отправка не удалась — не помечаем, повторим при следующем запуске.

    if sent:
        memory.mark_seen([e.id for e in new_entries])
        logger.info(f'Готово. Включено в дайджест: {len(new_entries)} записей.')
    else:
        logger.warning(
            'Дайджест не отправлен — память не обновлена. '
            'При следующем запуске попробуем снова.'
        )
