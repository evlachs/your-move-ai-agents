"""
core.py — главная логика агента
Цикл: observe → plan → act (diff) → act (ревью) → act (публикация) → observe
"""

import logging

from configs.config import load_config
from agent.memory import AgentMemory
from agent.tools import GitHubApiTool, YandexGPTTool
from agent.notifier import GitHubNotifier

logger = logging.getLogger(__name__)


def _review_key(pr_number: int, head_sha: str) -> str:
    """Уникальный ключ для конкретной версии PR (номер + SHA последнего коммита)."""
    return f'{pr_number}:{head_sha}'


def run():
    """
    Точка входа агента — вызывается из main.py/scheduler.py каждый час.

    Цикл:
      1. observe — получаем список открытых PR из GitHub
      2. plan    — фильтруем уже проревьюенные версии (по ключу номер:sha в SQLite)
                   Если PR получил новые коммиты — sha изменился, ревью проводится заново
      3. act     — для каждого нового PR получаем diff через GitHub API
      4. act     — передаём diff в YandexGPT, получаем Markdown-ревью
      5. act     — публикуем ревью в PR через GitHub API
      6. observe — помечаем версию PR как проревьюенную (только после успешной публикации)
    """
    config = load_config()

    memory = AgentMemory(config.db_path)
    github = GitHubApiTool(config)
    gpt = YandexGPTTool(config)
    notifier = GitHubNotifier(config)

    # ── Шаг 1: observe ──────────────────────────────────────────────

    open_prs = github.list_open_prs()
    reviewed_keys = memory.get_reviewed_keys()

    # ── Шаг 2: plan ─────────────────────────────────────────────────

    new_prs = [
        pr for pr in open_prs
        if _review_key(pr.number, pr.head_sha) not in reviewed_keys
    ]

    if not new_prs:
        logger.info('Нет PR, требующих ревью — агент завершает работу.')
        return

    logger.info(f'PR для ревью: {len(new_prs)}. Начинаем обработку...')

    # ── Шаги 3–5: act — diff, ревью, публикация ────────────────────

    for pr in new_prs:
        logger.info(f'Обрабатываем PR #{pr.number}: {pr.title}')

        # Шаг 3: diff
        pr.diff = github.get_diff(pr)
        if not pr.diff:
            # Помечаем как проревьюенный, чтобы не опрашивать GitHub снова на каждом запуске.
            # Если в PR появятся новые коммиты — head_sha изменится и ревью пройдёт заново.
            logger.warning(f'PR #{pr.number}: diff пустой (возможно, только бинарные файлы) — пропускаем и запоминаем.')
            memory.mark_reviewed(_review_key(pr.number, pr.head_sha))
            continue

        # Шаг 4: ревью
        pr.review = gpt.review_diff(pr)
        if not pr.review:
            logger.warning(f'PR #{pr.number}: GPT не вернул ревью — пропускаем.')
            continue

        # Шаг 5: публикация
        posted = notifier.post_review(pr)

        # ── Шаг 6: observe ──────────────────────────────────────────
        # Помечаем только после успешной публикации.
        # Если публикация не удалась — при следующем запуске попробуем снова.
        if posted:
            memory.mark_reviewed(_review_key(pr.number, pr.head_sha))
