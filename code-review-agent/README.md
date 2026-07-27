# Code Review Agent

ИИ-агент, который следит за открытыми Pull Request на GitHub, проводит автоматическое код-ревью через YandexGPT и публикует результат прямо в PR в виде комментария.

## Как это работает

Агент — это цикл (`agent/core.py`), который запускается раз в час:

1. **observe** — `GitHubApiTool` запрашивает список открытых PR репозитория через GitHub REST API. Если задан `GITHUB_BASE_BRANCH` — только PR в эту ветку.
2. **plan** — из списка убираем уже проревьюенные версии PR (по ключу `{number}:{head_sha}` в SQLite). Если в PR появились новые коммиты — `head_sha` изменился, и агент проведёт ревью заново.
3. **act (diff)** — для каждого нового PR загружаем список изменённых файлов с патчами. Diff обрезается до `MAX_DIFF_CHARS` символов, если он слишком большой.
4. **act (ревью)** — diff передаётся в `YandexGPTTool.review_diff()`: GPT анализирует изменения и возвращает структурированный Markdown-отчёт (что изменилось / проблемы / рекомендации).
5. **act (публикация)** — `GitHubNotifier` публикует ревью как PR review с типом `COMMENT` через GitHub API (не меняет статус PR, только добавляет комментарий).
6. **observe** — версия PR помечается как проревьюенная только после успешной публикации. Если API вернул ошибку — при следующем запуске попробуем снова.

## Память

`agent/memory.py` хранит в SQLite ключи вида `{pr_number}:{head_sha}`. Это гарантирует:
- Каждый PR ревьюируется ровно один раз для каждой версии кода.
- Если разработчик обновил ветку — агент проведёт ревью заново.

## Переменные окружения

См. `env.example`. Ключевые:

- `GITHUB_TOKEN` — Personal Access Token с правом `repo`, или Fine-grained token с правами `pull_requests: read+write` (обязательно).
- `GITHUB_REPO` — репозиторий в формате `owner/repo` (обязательно).
- `GITHUB_BASE_BRANCH` — ревьюить только PR в эту ветку (необязательно, по умолчанию все PR).
- `MAX_DIFF_CHARS` — максимальный размер diff для GPT (по умолчанию `8000`). Слишком большой diff даёт менее точное ревью.
- `YANDEX_API_KEY`, `YANDEX_FOLDER_ID` — доступ к YandexGPT.
- `YANDEX_GPT_MODEL` — рекомендуется `yandexgpt` (не lite) для более точного анализа кода.
- `CHECK_INTERVAL_HOURS` — как часто проверять новые PR (по умолчанию `1`).

## Запуск

Локально:

```bash
cp env.example .env   # заполнить своими значениями
pip install -r requirements.txt
mkdir -p data

python main.py --once   # один проход (для проверки)
python main.py          # планировщик — проверка каждый час
```

В Docker:

```bash
docker build -t code-review-agent .
docker run --env-file .env -v $(pwd)/data:/data code-review-agent
```

## Стек

- Python 3.11
- GitHub REST API — чтение PR и публикация ревью
- YandexGPT (REST API) — анализ diff и генерация ревью
- APScheduler — расписание
- SQLite — память между запусками
