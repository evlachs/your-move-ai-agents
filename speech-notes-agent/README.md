# Speech Notes Agent

ИИ-агент, который следит за папкой с аудиозаписями встреч, расшифровывает их через Yandex SpeechKit и присылает на email структурированные заметки: краткое резюме и список задач.

## Как это работает

Агент — это цикл (`agent/core.py`), который запускается раз в час:

1. **observe** — `AudioScannerTool` сканирует папку `AUDIO_DIR` на новые файлы (`.mp3`, `.ogg`, `.wav`, `.m4a`). Уже обработанные файлы отфильтровываются через память.
2. **plan** — если новых файлов нет, агент завершает работу до следующего запуска.
3. **act (расшифровка)** — каждый файл отправляется в `SpeechKitTool.recognize()`. SpeechKit работает асинхронно: агент отправляет файл, получает ID операции и ждёт результат, опрашивая статус каждые `SPEECHKIT_POLL_INTERVAL` секунд.
4. **act (анализ)** — транскрипт передаётся в `YandexGPTTool.analyze_transcript()` → получаем краткое резюме встречи и список задач в структурированном формате.
5. **act (отправка)** — `EmailNotifier` рендерит `templates/digest.html` и отправляет дайджест по всем обработанным записям через SMTP.
6. **observe** — файлы запоминаются в SQLite только после успешной отправки. Если письмо не ушло — следующий запуск повторит попытку.

## Память

`agent/memory.py` хранит в SQLite пути к уже обработанным файлам. Это гарантирует, что каждая запись попадёт в дайджест ровно один раз, даже если агент перезапустится.

## Переменные окружения

См. `env.example`. Ключевые:

- `AUDIO_DIR` — папка, которую агент сканирует на новые файлы.
- `AUDIO_EXTENSIONS` — список расширений через запятую (по умолчанию `.mp3,.ogg,.wav,.m4a`).
- `YANDEX_API_KEY`, `YANDEX_FOLDER_ID` — доступ к SpeechKit и YandexGPT.
- `SPEECHKIT_LANGUAGE` — язык распознавания (по умолчанию `ru-RU`).
- `SPEECHKIT_POLL_INTERVAL`, `SPEECHKIT_MAX_POLLS` — таймаут распознавания: `interval × max_polls` секунд (по умолчанию 10 минут).
- `SMTP_*`, `EMAIL_FROM`, `EMAIL_TO` — доставка дайджеста.
- `CHECK_INTERVAL_HOURS` — как часто проверять папку (по умолчанию каждый час).

## Запуск

Локально:

```bash
cp env.example .env   # заполнить своими значениями
pip install -r requirements.txt
mkdir -p audio data

# Положи аудиофайл встречи в папку audio/
cp /path/to/meeting.mp3 audio/

python main.py --once   # один проход цикла агента (для проверки)
python main.py          # планировщик — проверка папки каждый час
```

В Docker:

```bash
docker build -t speech-notes-agent .
docker run --env-file .env \
  -v $(pwd)/audio:/app/audio \
  -v $(pwd)/data:/data \
  speech-notes-agent
```

## Стек

- Python 3.11
- Yandex SpeechKit (REST API, асинхронное распознавание) — расшифровка аудио
- YandexGPT (REST API) — резюме и задачи из транскрипта
- Jinja2 + `smtplib` — рендер и отправка HTML-дайджеста
- APScheduler — расписание (раз в час)
- SQLite — память между запусками
