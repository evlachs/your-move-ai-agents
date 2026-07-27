"""
core.py — главная логика агента
Цикл: observe → plan → act (анализ) → act (отправка) → observe
"""

import logging

from configs.config import load_config
from agent.memory import AgentMemory
from agent.tools import HHApiTool, YandexGPTTool
from agent.notifier import EmailNotifier

logger = logging.getLogger(__name__)


def run():
    """
    Точка входа агента — вызывается из main.py/scheduler.py каждые N часов.

    Цикл:
      1. observe — запрашиваем свежие вакансии с HH.ru по фильтрам из конфига
      2. plan    — убираем уже виденные (по ID из SQLite), если новых нет — выходим
      3. act     — каждую новую вакансию оцениваем через YandexGPT
      4. act     — отправляем дайджест на email
      5. observe — сохраняем ID всех новых вакансий в память
                   (даже если GPT не дал оценку — чтобы не показывать снова)
    """
    config = load_config()

    memory = AgentMemory(config.db_path)
    hh = HHApiTool(config)
    gpt = YandexGPTTool(config)
    notifier = EmailNotifier(config)

    # ── Шаг 1: observe ──────────────────────────────────────────────

    all_vacancies = hh.search()
    seen_ids = memory.get_seen_ids()

    # ── Шаг 2: plan ─────────────────────────────────────────────────

    new_vacancies = [v for v in all_vacancies if v.id not in seen_ids]

    if not new_vacancies:
        logger.info('Новых вакансий нет — агент завершает работу.')
        return

    logger.info(f'Новых вакансий: {len(new_vacancies)}. Начинаем анализ...')

    # ── Шаг 3: act — анализ ─────────────────────────────────────────

    for vacancy in new_vacancies:
        logger.info(f'Анализируем: {vacancy.title} — {vacancy.employer}')
        vacancy.assessment, vacancy.key_points = gpt.analyze_vacancy(vacancy)

    # ── Шаг 4: act — отправка ───────────────────────────────────────

    sent = notifier.send_digest(new_vacancies, config.hh_search_text)

    # ── Шаг 5: observe — запись в память ────────────────────────────
    # Помечаем ВСЕ новые вакансии, даже те, по которым GPT не дал оценку.
    # Цель памяти — не показывать одно и то же дважды, а не фильтровать по качеству.
    # Если дайджест не ушёл — не помечаем: при следующем запуске попробуем снова.

    if sent:
        memory.mark_seen([v.id for v in new_vacancies])
        logger.info(f'Готово. Показано вакансий: {len(new_vacancies)}.')
    else:
        logger.warning(
            'Дайджест не отправлен — память не обновлена. '
            'При следующем запуске попробуем снова.'
        )
