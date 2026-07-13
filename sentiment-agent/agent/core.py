"""
core.py — главный цикл агента анализа тональности.

Цикл observe → plan → act:
  1. observe  : загрузить отзывы из Google Sheets
  2. plan     : отфильтровать уже проанализированные (по ID в SQLite)
  3. act      : отправить каждый новый отзыв в YandexGPT → получить тональность и темы
  4. act      : сгенерировать итоговое резюме по всей выборке
  5. act      : отправить HTML-отчёт на email
  6. observe  : пометить все обработанные отзывы в памяти
"""

import logging

from configs.config import load_config
from agent.memory import AgentMemory
from agent.tools import SheetsFetcherTool, YandexGPTTool, Review
from agent.notifier import EmailNotifier

logger = logging.getLogger(__name__)


def run():
    """Один полный проход цикла агента. Вызывается планировщиком."""
    logger.info('=== Запуск агента тональности ===')

    config = load_config()
    memory = AgentMemory(config.db_path)
    fetcher = SheetsFetcherTool(config)
    gpt = YandexGPTTool(config)
    notifier = EmailNotifier(config)

    # Шаг 1 (observe): загружаем все отзывы из таблицы
    all_reviews = fetcher.fetch()
    if not all_reviews:
        logger.info('Нет отзывов для обработки.')
        return

    # Шаг 2 (plan): оставляем только новые, не превышая лимит
    analyzed_ids = memory.get_analyzed_ids()
    new_reviews: list[Review] = [
        r for r in all_reviews if r.id not in analyzed_ids
    ][: config.max_reviews_per_run]

    if not new_reviews:
        logger.info('Новых отзывов нет — пропускаем.')
        return

    logger.info(f'Новых отзывов к анализу: {len(new_reviews)}.')

    # Шаг 3 (act): анализируем тональность каждого отзыва
    failed_ids: list[str] = []
    for i, review in enumerate(new_reviews, 1):
        sentiment, topics = gpt.analyze_review(review)
        if not sentiment:
            logger.warning(f'Отзыв {i}/{len(new_reviews)}: GPT не вернул тональность — пропускаем.')
            failed_ids.append(review.id)
            continue
        review.sentiment = sentiment
        review.topics = topics
        logger.debug(f'Отзыв {i}/{len(new_reviews)}: [{sentiment}] {review.text[:60]}...')

    # Убираем отзывы с ошибкой GPT из выборки для отчёта
    analyzed: list[Review] = [r for r in new_reviews if r.id not in failed_ids]

    if not analyzed:
        logger.warning('Все отзывы завершились с ошибкой GPT — отчёт не отправляется.')
        return

    # Шаг 4 (act): генерируем итоговое резюме по всей выборке
    summary = gpt.generate_summary(analyzed)
    if not summary:
        logger.warning('GPT не вернул резюме — отправим отчёт без него.')

    # Шаг 5 (act): отправляем отчёт на email
    sent = notifier.send(analyzed, summary)
    if not sent:
        logger.error('Не удалось отправить отчёт — обработанные отзывы НЕ сохраняются в памяти.')
        return

    # Шаг 6 (observe): помечаем успешно обработанные отзывы в памяти
    memory.mark_analyzed([r.id for r in analyzed])

    logger.info(f'=== Готово. Отправлен отчёт по {len(analyzed)} отзывам. ===')
