"""
core.py — главная логика агента
ReAct цикл: observe → plan → act → observe
"""

import logging

from configs.config import load_config
from agent.memory import AgentMemory
from agent.tools import GitHubTool, YandexGPTTool
from agent.notifier import EmailNotifier

logger = logging.getLogger(__name__)


def run():
    """
    Точка входа агента — вызывается из scheduler.py каждый день.

    Цикл:
      1. observe  — получаем PR и коммиты из GitHub
      2. plan     — фильтруем уже виденные через SQLite
      3. act      — анализируем через YandexGPT
      4. act      — отправляем дайджест на email
      5. observe  — запоминаем отправленное в SQLite
    """
    config = load_config()

    memory   = AgentMemory(config.db_path)
    github   = GitHubTool(config)
    gpt      = YandexGPTTool(config)
    notifier = EmailNotifier(config)

    repo = config.github_repo
    logger.info(f'Агент запущен. Репозиторий: {repo}')

    # ── Шаг 1: observe ──────────────────────────────────────────────
    # Агент смотрит что произошло в репозитории за последние 24 часа

    all_prs     = github.get_new_pull_requests(since_hours=24)
    all_commits = github.get_new_commits(since_hours=24)

    logger.info(f'GitHub вернул: {len(all_prs)} PR, {len(all_commits)} коммитов')

    # ── Шаг 2: plan ─────────────────────────────────────────────────
    # Сравниваем с памятью — оставляем только то что ещё не отправляли

    new_prs     = memory.filter_new_prs(all_prs, repo)
    new_commits = memory.filter_new_commits(all_commits, repo)

    logger.info(
        f'После фильтрации памяти: {len(new_prs)} новых PR, '
        f'{len(new_commits)} новых коммитов'
    )

    if not new_prs and not new_commits:
        logger.info('Новых событий нет — агент завершает работу.')
        return

    # ── Шаг 3: act — анализ ─────────────────────────────────────────
    # YandexGPT анализирует каждый PR и коммиты как паттерн

    for pr in new_prs:
        logger.info(f'Анализируем PR #{pr.number}: {pr.title}')
        pr.analysis = gpt.analyze_pr(pr)

    commits_summary = ''
    if new_commits:
        logger.info(f'Анализируем {len(new_commits)} коммитов...')
        commits_summary = gpt.analyze_commits(new_commits)

    subject_line = gpt.generate_digest_summary(repo, new_prs, new_commits)

    # ── Шаг 4: act — уведомление ────────────────────────────────────
    # Отправляем дайджест. Только если письмо ушло — пишем в память.

    sent = notifier.send_digest(
        repo=repo,
        new_prs=new_prs,
        new_commits=new_commits,
        commits_summary=commits_summary,
        subject_line=subject_line,
    )

    # ── Шаг 5: observe — запись в память ────────────────────────────
    # Важно: запоминаем ТОЛЬКО после успешной отправки.
    # Если письмо не ушло — при следующем запуске попробуем снова.

    if sent:
        memory.mark_prs_seen_bulk(new_prs, repo)
        memory.mark_commits_seen_bulk(new_commits, repo)

        stats = memory.stats(repo)
        logger.info(
            f'Готово. Всего в памяти: '
            f'{stats["seen_prs"]} PR, {stats["seen_commits"]} коммитов'
        )
    else:
        logger.warning(
            'Письмо не отправлено — память не обновлена. '
            'При следующем запуске попробуем снова.'
        )
