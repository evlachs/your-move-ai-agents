"""
core.py — главная логика агента
ReAct цикл: observe → plan → act (анализ) → act (генерация) → act (публикация) → observe
"""

import logging

from configs.config import load_config
from agent.memory import AgentMemory
from agent.scanner import ProjectScanner
from agent.tools import GitHubTool, YandexGPTTool

logger = logging.getLogger(__name__)


def run():
    """
    Точка входа агента — вызывается из main.py/scheduler.py.

    Цикл:
      1. observe — узнаём текущий HEAD целевого репозитория
      2. plan    — сравниваем с памятью: код менялся с прошлого раза?
      3. act     — строим карту проекта и анализируем изменения
      4. act     — генерируем README.md и документацию через YandexGPT
      5. act     — публикуем ветку с изменениями и открываем PR
      6. observe — запоминаем SHA коммита (только после успешного PR)
    """
    config = load_config()

    memory  = AgentMemory(config.db_path)
    github  = GitHubTool(config)
    gpt     = YandexGPTTool(config)
    scanner = ProjectScanner(github)

    repo = config.target_repo
    logger.info(f'Агент запущен. Целевой репозиторий: {repo}')

    # ── Шаг 1: observe ──────────────────────────────────────────────
    # Узнаём текущий HEAD ветки, которую документируем

    head_sha = github.get_head_sha()
    last_sha = memory.get_last_commit_sha(repo)

    logger.info(f'HEAD: {head_sha[:7]}, последний обработанный: {last_sha[:7] if last_sha else "нет"}')

    # ── Шаг 2: plan ─────────────────────────────────────────────────
    # Если код не менялся с прошлого запуска — делать нечего

    if last_sha == head_sha:
        logger.info('Изменений в репозитории нет — агент завершает работу.')
        return

    changed_files = github.compare_commits(last_sha, head_sha) if last_sha else []
    if last_sha:
        logger.info(f'Изменено файлов с прошлой генерации: {len(changed_files)}')
    else:
        logger.info('Первый запуск для этого репозитория — выполняем полный анализ.')

    # ── Шаг 3: act — анализ ─────────────────────────────────────────
    # Строим карту проекта и читаем текущие README/документацию

    project_map = scanner.build_project_map(head_sha)
    existing_readme = github.get_file_content('README.md', head_sha) or ''
    existing_doc = github.get_file_content(config.doc_path, head_sha) or ''

    # ── Шаг 4: act — генерация ──────────────────────────────────────
    # YandexGPT генерирует обновлённые README, документацию и описание PR

    logger.info('Генерируем README.md...')
    new_readme = gpt.generate_readme(project_map, existing_readme, changed_files)

    logger.info('Генерируем документацию...')
    new_doc = gpt.generate_documentation(project_map, existing_doc, changed_files)

    if not new_readme or not new_doc:
        logger.warning('YandexGPT не вернул текст — память не обновлена. Попробуем при следующем запуске.')
        return

    pr_description = gpt.generate_pr_description(repo, changed_files)

    # ── Шаг 5: act — публикация ──────────────────────────────────────
    # Создаём ветку, коммитим изменения, открываем Pull Request

    branch_name = f'docs/auto-update-{head_sha[:7]}'

    try:
        github.create_branch(branch_name, head_sha)
        github.commit_file(branch_name, 'README.md', new_readme, 'docs: обновление README.md (авто)')
        github.commit_file(branch_name, config.doc_path, new_doc, 'docs: обновление документации (авто)')
        pr_url = github.open_pull_request(
            branch=branch_name,
            title='docs: автоматическое обновление документации',
            body=pr_description,
        )
        logger.info(f'Pull Request создан: {pr_url}')

    except Exception as e:
        logger.error(f'Не удалось опубликовать документацию: {e}', exc_info=True)
        logger.warning('Память не обновлена — при следующем запуске попробуем снова.')
        return

    # ── Шаг 6: observe — запись в память ────────────────────────────
    # Важно: запоминаем ТОЛЬКО после успешного создания PR

    memory.set_last_commit_sha(repo, head_sha)
    logger.info('Готово.')
