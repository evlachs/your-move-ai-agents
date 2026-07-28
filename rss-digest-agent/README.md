# RSS Digest Agent

ИИ-агент, который раз в день читает заданные RSS/Atom-ленты, суммаризирует новые статьи через YandexGPT и присылает на email сгруппированный дайджест.

## Как это работает

Агент — это цикл (`agent/core.py`), который запускается каждое утро в заданное время:

1. **observe** — `RSSFetcherTool` загружает все ленты из `RSS_FEEDS` через `feedparser`. Из каждой ленты берёт не более `MAX_ENTRIES_PER_FEED` последних записей.
2. **plan** — из полученных записей выбрасываем уже виденные (по ID из SQLite). Если новых нет — агент завершает работу.
3. **act (суммаризация)** — каждая новая запись передаётся в `YandexGPTTool.summarize()`: GPT пишет краткое резюме в 1-2 предложения. Если `DIGEST_TOPICS` заполнен — GPT учитывает тематику как контекст.
4. **act (отправка)** — `EmailNotifier` рендерит `templates/digest.html`, группируя статьи по названию ленты, и отправляет через SMTP.
5. **observe** — ID всех новых записей сохраняются в SQLite. Если отправка не удалась — память не обновляется, при следующем запуске попробуем снова.

## Память

`agent/memory.py` хранит в SQLite ID уже показанных записей (guid или ссылка). Это исключает дубли между ежедневными дайджестами и переживает перезапуски контейнера.

## Переменные окружения

См. `env.example`. Ключевые:

- `RSS_FEEDS` — URL-адреса лент через `;`, например `https://habr.com/ru/rss/best/daily/;https://example.com/feed` (обязательно).
- `MAX_ENTRIES_PER_FEED` — сколько последних записей брать из каждой ленты (по умолчанию `20`). Ограничивает объём, особенно при первом запуске.
- `DIGEST_TOPICS` — тематический контекст для GPT (необязательно), например `Python, ИИ, стартапы`.
- `YANDEX_API_KEY`, `YANDEX_FOLDER_ID` — доступ к YandexGPT.
- `SMTP_*`, `EMAIL_FROM`, `EMAIL_TO` — доставка дайджеста.
- `DIGEST_HOUR`, `DIGEST_MINUTE`, `TIMEZONE` — время ежедневного запуска (по умолчанию `09:00 Europe/Moscow`).

## Запуск

Локально:

```bash
cp env.example .env   # заполнить своими значениями
pip install -r requirements.txt
mkdir -p data

python main.py --once   # один проход цикла агента (для проверки)
python main.py          # планировщик — дайджест каждый день в заданное время
```

В Docker:

```bash
docker build -t rss-digest-agent .
docker run --env-file .env -v $(pwd)/data:/data rss-digest-agent
```

## Стек

- Python 3.11
- `feedparser` — парсинг RSS/Atom-лент (поддерживает RSS 0.9x, 2.0, Atom)
- YandexGPT (REST API) — суммаризация статей
- Jinja2 + `smtplib` — рендер и отправка HTML-дайджеста
- APScheduler — расписание (раз в день)
- SQLite — память между запусками
