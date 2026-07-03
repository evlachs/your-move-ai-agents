# Log Analysis Agent

ИИ-агент, который каждый час читает логи из Yandex Cloud Logging, считает статистику по уровням и присылает дайджест с анализом ошибок от YandexGPT.

## Как это работает

Агент — это цикл (`agent/core.py`), который запускается раз в час (или по команде):

1. **observe** — `LogFetcherTool` запрашивает записи лог-группы за период с прошлой проверки (постранично, по `nextPageToken`).
2. **plan** — если новых записей нет, агент всё равно сдвигает границу периода в памяти (чтобы окно не растягивалось бесконечно) и завершает работу.
3. **act (статистика + анализ)** — считаем количество записей по уровням (`ERROR`, `FATAL`, `WARN`, `INFO`, ...) обычным `Counter`, берём до 20 примеров `ERROR`/`FATAL`-сообщений и отправляем их в `YandexGPTTool.analyze_logs()` — получаем краткий анализ: что не так, есть ли повторяющийся паттерн.
4. **act (тема)** — генерируется тема письма-дайджеста.
5. **act (отправка)** — `EmailNotifier` рендерит `templates/digest.html` (таблица по уровням + анализ + примеры ошибок) и отправляет через SMTP.
6. **observe** — память обновляется (новая граница периода) только после успешной отправки. Если отправка не удалась — следующий запуск повторит то же окно.

## Память

`agent/memory.py` хранит в SQLite границу времени (`until` предыдущего запуска) по `log_group_id` — это не даёт окнам анализа пересекаться или образовывать пропуски между запусками.

## Переменные окружения

См. `env.example`. Ключевые:

- `YC_IAM_TOKEN` — IAM-токен для Yandex Cloud Logging API (`yc iam create-token`). Токен живёт около 12 часов — для длительной непрерывной работы агента его нужно периодически обновлять (это известное ограничение учебного агента, без автоматического рефреша).
- `LOG_GROUP_ID` — ID группы логов (Yandex Cloud Console → Cloud Logging).
- `YANDEX_API_KEY`, `YANDEX_FOLDER_ID` — доступ к YandexGPT.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO` — доставка дайджеста.
- `CHECK_INTERVAL_HOURS` — как часто проверять логи (по умолчанию 1).

## Запуск

Локально:

```bash
cp env.example .env   # заполнить своими значениями
pip install -r requirements.txt

python main.py --once   # один проход цикла агента (для проверки/ручного запуска)
python main.py          # планировщик — запуск каждые CHECK_INTERVAL_HOURS часов
```

В Docker:

```bash
docker build -t log-analysis-agent .
docker run --env-file .env -v $(pwd)/data:/data log-analysis-agent
```

## Стек

- Python 3.11
- Yandex Cloud Logging (REST API) — чтение записей логов
- YandexGPT (REST API) — анализ ошибок и тема дайджеста
- Jinja2 + `smtplib` — рендер и отправка HTML-дайджеста
- APScheduler (`IntervalTrigger`) — запуск раз в N часов
- SQLite — память между запусками
