"""
core.py — главная логика агента
Цикл: observe → plan → act (расшифровка) → act (анализ) → act (отправка) → observe
"""

import logging
from datetime import datetime

from configs.config import load_config
from agent.memory import AgentMemory
from agent.tools import AudioScannerTool, SpeechKitTool, YandexGPTTool, MeetingNotes
from agent.notifier import EmailNotifier

logger = logging.getLogger(__name__)


def run():
    """
    Точка входа агента — вызывается из main.py/scheduler.py каждый час.

    Цикл:
      1. observe — сканируем папку с аудиофайлами, фильтруем уже обработанные
      2. plan    — если новых файлов нет, завершаем работу
      3. act     — каждый файл расшифровываем через SpeechKit
      4. act     — транскрипт анализируем через YandexGPT: резюме + задачи
      5. act     — отправляем дайджест заметок на email
      6. observe — запоминаем обработанные файлы (только после успешной отправки)
    """
    config = load_config()

    memory = AgentMemory(config.db_path)
    scanner = AudioScannerTool(config)
    speechkit = SpeechKitTool(config)
    gpt = YandexGPTTool(config)
    notifier = EmailNotifier(config)

    # ── Шаг 1: observe ──────────────────────────────────────────────

    processed = memory.get_processed_files()
    new_files = scanner.scan(processed)

    # ── Шаг 2: plan ─────────────────────────────────────────────────

    if not new_files:
        logger.info('Новых аудиофайлов нет — агент завершает работу.')
        return

    logger.info(f'Найдено новых файлов: {len(new_files)}. Начинаем обработку...')

    # ── Шаг 3–4: act — расшифровка и анализ ────────────────────────

    results: list[MeetingNotes] = []
    failed_paths: list[str] = []

    for file_path in new_files:
        logger.info(f'Обрабатываем: {file_path.name}')

        try:
            transcript = speechkit.recognize(file_path)
        except TimeoutError as e:
            logger.error(str(e))
            failed_paths.append(str(file_path.resolve()))
            continue

        if not transcript:
            logger.warning(f'Транскрипт пустой для {file_path.name} — файл будет пропущен и обработан при следующем запуске.')
            failed_paths.append(str(file_path.resolve()))
            continue

        summary, tasks = gpt.analyze_transcript(transcript, file_path.name)

        results.append(MeetingNotes(
            file_name=file_path.name,
            file_path=str(file_path.resolve()),
            processed_at=datetime.now(),
            transcript=transcript,
            summary=summary,
            tasks=tasks,
        ))

    if failed_paths:
        logger.warning(f'Не удалось обработать файлов: {len(failed_paths)}. Они будут повторно обработаны при следующем запуске.')

    # ── Шаг 5: act — отправка ────────────────────────────────────────

    if not results:
        logger.info('Нет успешно обработанных файлов — дайджест не отправляем.')
        return

    sent = notifier.send_digest(results)

    # ── Шаг 6: observe — запись в память ────────────────────────────
    # Запоминаем ТОЛЬКО успешно расшифрованные файлы и ТОЛЬКО после отправки.
    # Файлы с ошибкой расшифровки (failed_paths) не помечаем — попробуем снова.

    if sent:
        for notes in results:
            memory.add_processed_file(notes.file_path)
        logger.info(f'Готово. Обработано файлов: {len(results)}')
    else:
        logger.warning(
            'Дайджест не отправлен — память не обновлена. '
            'При следующем запуске попробуем снова.'
        )
