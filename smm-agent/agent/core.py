"""
core.py — главная логика агента
Цикл: plan → act (тема) → act (текст) → act (картинка) → act (черновик в VK) → observe
"""

import logging

from configs.config import load_config
from agent.memory import AgentMemory
from agent.tools import YandexGPTTool, YandexARTTool, VKTool, next_publish_datetime

logger = logging.getLogger(__name__)


def run():
    """
    Точка входа агента — вызывается из main.py/scheduler.py.

    Цикл:
      1. plan — на завтра уже есть черновик? Если да — выходим.
      2. act  — выбираем тему, избегая повторов из памяти
      3. act  — генерируем текст поста через YandexGPT
      4. act  — генерируем изображение через YandexART
      5. act  — загружаем фото и создаём отложенную запись в VK
      6. observe — запоминаем черновик (только после успешной публикации)
    """
    config = load_config()

    memory = AgentMemory(config.db_path)
    gpt    = YandexGPTTool(config)
    art    = YandexARTTool(config)
    vk     = VKTool(config)

    publish_at = next_publish_datetime(config.publish_hour, config.timezone)
    logger.info(f'Агент запущен. Целевая дата публикации черновика: {publish_at.isoformat()}')

    # ── Шаг 1: plan ─────────────────────────────────────────────────
    # Если на эту дату уже есть черновик — повторный запуск не нужен

    if memory.has_post_for(publish_at.isoformat()):
        logger.info('Черновик на эту дату уже подготовлен — агент завершает работу.')
        return

    # ── Шаг 2: act — тема ────────────────────────────────────────────

    recent_topics = memory.recent_topics(limit=20)
    topic = gpt.choose_topic(recent_topics)
    logger.info(f'Выбрана тема: {topic}')

    # ── Шаг 3: act — текст поста ─────────────────────────────────────

    post_text = gpt.generate_post_text(topic)
    if not post_text:
        logger.warning('YandexGPT не вернул текст поста — память не обновлена. Попробуем при следующем запуске.')
        return

    # ── Шаг 4: act — изображение ──────────────────────────────────────

    logger.info('Генерируем изображение через YandexART...')
    image_bytes = art.generate_image(topic)
    if not image_bytes:
        logger.warning('YandexART не вернул изображение — память не обновлена. Попробуем при следующем запуске.')
        return

    # ── Шаг 5: act — публикация черновика в VK ─────────────────────────

    try:
        attachment = vk.upload_and_attach_photo(image_bytes)
        vk_post_id = vk.create_postponed_post(post_text, attachment, publish_at)
        logger.info(f'Отложенная запись создана в VK: post_id={vk_post_id}')

    except Exception as e:
        logger.error(f'Не удалось создать отложенную запись в VK: {e}', exc_info=True)
        logger.warning('Память не обновлена — при следующем запуске попробуем снова.')
        return

    # ── Шаг 6: observe — запись в память ────────────────────────────
    # Важно: запоминаем ТОЛЬКО после успешного создания записи в VK

    memory.save_post(topic, post_text, vk_post_id, publish_at.isoformat())
    logger.info('Готово.')
