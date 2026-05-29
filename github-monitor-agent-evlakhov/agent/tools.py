"""
tools.py — инструменты агента
Каждая функция — отдельный инструмент который агент вызывает в цикле.
GitHub API: получаем PR и коммиты
YandexGPT: анализируем и суммаризируем изменения
"""

import logging

import requests
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from github import Github, GithubException
from openai import OpenAI

from configs.config import Config


logger = logging.getLogger(__name__)


# --- Структуры данных ---

@dataclass
class PRInfo:
    number: int
    title: str
    author: str
    url: str
    created_at: datetime
    body: str
    changed_files: int
    additions: int
    deletions: int
    analysis: str = ''   # заполняется YandexGPT


@dataclass
class CommitInfo:
    sha: str
    short_sha: str
    message: str
    author: str
    url: str
    committed_at: datetime
    analysis: str = ''   # заполняется YandexGPT


# --- Инструмент 1: GitHub API ---

class GitHubTool:
    """
    Инструмент для работы с GitHub.
    Агент вызывает его чтобы узнать что изменилось в репозитории.
    """

    def __init__(self, config: Config):
        self.github = Github(config.github_token)
        self.repo_name = config.github_repo
        self.github_branch = config.github_branch
        self._repo = None

    @property
    def repo(self):
        """Ленивая загрузка репозитория — один раз при первом обращении."""
        if self._repo is None:
            self._repo = self.github.get_repo(self.repo_name)
        return self._repo

    def get_new_pull_requests(self, since_hours: int = 24) -> list[PRInfo]:
        """
        Возвращает PR открытые за последние N часов.
        Агент вызывает это как первый шаг наблюдения (observe).
        """
        since = datetime.now(timezone.utc) - timedelta(hours=since_hours)

        try:
            pulls = self.repo.get_pulls(
                state='open',
                sort='created',
                direction='desc',
            )

            result = []
            for pr in pulls:
                # GitHub API отдаёт в порядке убывания — останавливаемся
                # как только дошли до старых PR
                if pr.created_at.replace(tzinfo=timezone.utc) < since:
                    break

                result.append(PRInfo(
                    number=pr.number,
                    title=pr.title,
                    author=pr.user.login,
                    url=pr.html_url,
                    created_at=pr.created_at,
                    body=(pr.body or '')[:500],  # обрезаем длинные описания
                    changed_files=pr.changed_files,
                    additions=pr.additions,
                    deletions=pr.deletions,
                ))

            logger.info(f'GitHub: найдено {len(result)} новых PR за {since_hours}ч')
            return result

        except GithubException as e:
            logger.error(f'Ошибка GitHub API при получении PR: {e}')
            return []

    def get_new_commits(self, since_hours: int = 24) -> list[CommitInfo]:
        """
        Возвращает коммиты в основную ветку за последние N часов.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=since_hours)

        try:
            commits = self.repo.get_commits(
                since=since,
                sha=self.github_branch,
            )

            result = []
            for commit in commits:
                msg = commit.commit.message
                result.append(CommitInfo(
                    sha=commit.sha,
                    short_sha=commit.sha[:7],
                    message=msg.split('\n')[0],  # только первая строка
                    author=commit.commit.author.name,
                    url=commit.html_url,
                    committed_at=commit.commit.author.date,
                ))

            logger.info(f'GitHub: найдено {len(result)} новых коммитов за {since_hours}ч')
            return result

        except GithubException as e:
            logger.error(f'Ошибка GitHub API при получении коммитов: {e}')
            return []


# --- Инструмент 2: YandexGPT ---

class YandexGPTTool:
    """
    Инструмент для анализа изменений через YandexGPT.
    Использует openai-клиент с яндексовым base_url —
    это стандартный паттерн для OpenAI-совместимых API.
    """

    # Модели YandexGPT (от лёгкой к тяжёлой)
    MODEL_LITE = 'yandexgpt-lite'
    MODEL_PRO  = 'yandexgpt'

    def __init__(self, config: Config):
        self.config = config
        self.folder_id = config.yandex_folder_id
        self.client = OpenAI(
            api_key=config.yandex_api_key,
            base_url='https://llm.api.cloud.yandex.net/foundationModels/v1',
        )

    def _chat(self, system: str, user: str, model: str = MODEL_LITE) -> str:
        try:
            response = requests.post(
                'https://llm.api.cloud.yandex.net/foundationModels/v1/completion',
                headers={
                    'Authorization': f'Api-Key {self.config.yandex_api_key}',
                    'x-folder-id': self.folder_id,
                },
                json={
                    'modelUri': f'gpt://{self.folder_id}/{model}',
                    'completionOptions': {
                        'temperature': 0.3,
                        'maxTokens': 500,
                    },
                    'messages': [
                        {'role': 'system', 'text': system},
                        {'role': 'user', 'text': user},
                    ],
                },
                timeout=30,
            )
            if not response.ok:
                logger.error(f'YandexGPT ответ: {response.text}')
                response.raise_for_status()
            return response.json()['result']['alternatives'][0]['message']['text']

        except Exception as e:
            logger.error(f'Ошибка YandexGPT: {e}')
            return 'Анализ недоступен.'

    def analyze_pr(self, pr: PRInfo) -> str:
        """
        Анализирует один PR и возвращает краткое резюме на русском.
        Агент вызывает это для каждого нового PR.
        """
        system = (
            'Ты технический аналитик. Анализируй Pull Request кратко и по делу. '
            'Отвечай на русском языке. Максимум 2-3 предложения.'
        )
        user = (
            f'PR #{pr.number}: {pr.title}\n'
            f'Автор: {pr.author}\n'
            f'Изменено файлов: {pr.changed_files}, '
            f'добавлено строк: {pr.additions}, удалено: {pr.deletions}\n'
            f'Описание: {pr.body or "не указано"}\n\n'
            'Оцени: что делает этот PR, насколько он значимый, '
            'есть ли риски?'
        )
        return self._chat(system, user)

    def analyze_commits(self, commits: list[CommitInfo]) -> str:
        """
        Анализирует список коммитов и возвращает общую сводку.
        Один вызов на весь список — экономим токены.
        """
        if not commits:
            return ''

        commit_list = '\n'.join(
            f'- {c.short_sha}: {c.message} ({c.author})'
            for c in commits
        )

        system = (
            'Ты технический аналитик. Анализируй коммиты кратко. '
            'Отвечай на русском языке. Максимум 3-4 предложения.'
        )
        user = (
            f'Коммиты за последние 24 часа ({len(commits)} шт.):\n'
            f'{commit_list}\n\n'
            'Кратко: что происходит в репозитории? '
            'Есть ли тревожные паттерны (много фиксов, рефакторинг, срочные изменения)?'
        )
        return self._chat(system, user)

    def generate_digest_summary(
        self,
        repo: str,
        new_prs: list[PRInfo],
        new_commits: list[CommitInfo],
    ) -> str:
        """
        Финальный шаг: общее резюме дайджеста одной фразой для темы письма.
        """
        if not new_prs and not new_commits:
            return 'Изменений не обнаружено'

        parts = []
        if new_prs:
            parts.append(f'{len(new_prs)} новых PR')
        if new_commits:
            parts.append(f'{len(new_commits)} коммитов')

        activity = ', '.join(parts)

        system = 'Ты пишешь тему для email. Одна фраза, максимум 60 символов, на русском.'
        user = (
            f'Репозиторий {repo}. За сутки: {activity}. '
            'Напиши тему письма-дайджеста.'
        )
        return self._chat(system, user)
