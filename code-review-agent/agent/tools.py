"""
tools.py — инструменты агента
GitHubApiTool : получает открытые PR и их diff через GitHub REST API.
YandexGPTTool : проводит код-ревью по diff, возвращает Markdown-отчёт.
"""

import logging
from dataclasses import dataclass

import requests

from configs.config import Config

logger = logging.getLogger(__name__)

GITHUB_API_URL = 'https://api.github.com'
YANDEX_GPT_URL = 'https://llm.api.cloud.yandex.net/foundationModels/v1/completion'


@dataclass
class PullRequest:
    number: int
    title: str
    author: str
    head_sha: str      # SHA последнего коммита — используется как часть ключа памяти
    base_branch: str   # целевая ветка PR
    url: str
    diff: str = ''     # заполняется через get_diff()
    review: str = ''   # заполняется YandexGPTTool


# --- Инструмент 1: GitHub API ---

class GitHubApiTool:
    """
    Инструмент для работы с GitHub REST API.
    Агент вызывает его чтобы получить список PR и их diff.
    """

    def __init__(self, config: Config):
        self.repo = config.github_repo
        self.base_branch = config.github_base_branch
        self.max_diff_chars = config.max_diff_chars
        self._headers = {
            'Authorization': f'token {config.github_token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        }

    def list_open_prs(self) -> list[PullRequest]:
        """
        Возвращает список открытых PR репозитория.
        Если GITHUB_BASE_BRANCH задан — только PR в эту ветку.
        """
        params = {'state': 'open', 'per_page': 50}
        if self.base_branch:
            params['base'] = self.base_branch

        try:
            response = requests.get(
                f'{GITHUB_API_URL}/repos/{self.repo}/pulls',
                headers=self._headers,
                params=params,
                timeout=15,
            )
            response.raise_for_status()
            items = response.json()
        except requests.HTTPError as e:
            logger.error(f'GitHub API ошибка (HTTP {e.response.status_code}): {e.response.text}')
            return []
        except Exception as e:
            logger.error(f'GitHub API ошибка: {e}')
            return []

        prs = [self._parse_pr(item) for item in items]
        if len(prs) == params['per_page']:
            logger.warning(
                f'GitHub: получено ровно {len(prs)} PR — возможно, есть ещё. '
                'Пагинация не реализована; увеличьте per_page или сократите количество открытых PR.'
            )
        else:
            logger.info(f'GitHub: найдено {len(prs)} открытых PR в {self.repo}.')
        return prs

    def get_diff(self, pr: PullRequest) -> str:
        """
        Получает diff PR: список изменённых файлов с патчами.
        Возвращает склеенный текст diff, обрезанный до max_diff_chars.
        """
        try:
            response = requests.get(
                f'{GITHUB_API_URL}/repos/{self.repo}/pulls/{pr.number}/files',
                headers=self._headers,
                params={'per_page': 100},
                timeout=15,
            )
            response.raise_for_status()
            files = response.json()
        except requests.HTTPError as e:
            logger.error(f'GitHub API ошибка при получении diff PR #{pr.number} (HTTP {e.response.status_code}): {e.response.text}')
            return ''
        except Exception as e:
            logger.error(f'GitHub API ошибка при получении diff PR #{pr.number}: {e}')
            return ''

        parts = []
        for f in files:
            filename = f.get('filename', '')
            patch = f.get('patch', '')
            if patch:
                parts.append(f'--- {filename} ---\n{patch}')

        diff = '\n\n'.join(parts)

        if len(diff) > self.max_diff_chars:
            diff = diff[: self.max_diff_chars] + '\n\n[... diff обрезан из-за размера ...]'

        return diff

    @staticmethod
    def _parse_pr(item: dict) -> PullRequest:
        return PullRequest(
            number=item.get('number', 0),
            title=item.get('title', ''),
            author=(item.get('user') or {}).get('login', ''),
            head_sha=(item.get('head') or {}).get('sha', ''),
            base_branch=(item.get('base') or {}).get('ref', ''),
            url=item.get('html_url', ''),
        )


# --- Инструмент 2: YandexGPT ---

class YandexGPTTool:
    """Инструмент для автоматического код-ревью через YandexGPT."""

    def __init__(self, config: Config):
        self.api_key = config.yandex_api_key
        self.folder_id = config.yandex_folder_id
        self.model = config.yandex_gpt_model

    def _chat(self, system: str, user: str, max_tokens: int = 800) -> str:
        try:
            response = requests.post(
                YANDEX_GPT_URL,
                headers={
                    'Authorization': f'Api-Key {self.api_key}',
                    'x-folder-id': self.folder_id,
                },
                json={
                    'modelUri': f'gpt://{self.folder_id}/{self.model}',
                    'completionOptions': {
                        'temperature': 0.2,
                        'maxTokens': max_tokens,
                    },
                    'messages': [
                        {'role': 'system', 'text': system},
                        {'role': 'user', 'text': user},
                    ],
                },
                timeout=60,
            )
            response.raise_for_status()
            return response.json()['result']['alternatives'][0]['message']['text'].strip()
        except requests.HTTPError as e:
            logger.error(f'YandexGPT ошибка (HTTP {e.response.status_code}): {e.response.text}')
            return ''
        except Exception as e:
            logger.error(f'YandexGPT ошибка: {e}')
            return ''

    def review_diff(self, pr: PullRequest) -> str:
        """
        Проводит код-ревью по diff PR.
        Возвращает Markdown-текст ревью для публикации в GitHub.
        Если GPT не ответил — возвращает пустую строку.
        """
        if not pr.diff:
            return ''

        system = (
            'Ты опытный разработчик, проводящий код-ревью. '
            'Проанализируй предоставленный diff и напиши структурированный отзыв на русском языке. '
            'Используй Markdown. Будь конкретным: указывай имена файлов и строки где это уместно. '
            'Структура ответа строго такая:\n'
            '## Что изменилось\n'
            '<краткое описание изменений>\n\n'
            '## Проблемы\n'
            '<баги, уязвимости, проблемы с производительностью или читаемостью — или "Серьёзных проблем не обнаружено">\n\n'
            '## Рекомендации\n'
            '<конкретные улучшения — или "Нет дополнительных рекомендаций">'
        )
        user = (
            f'PR #{pr.number}: {pr.title}\n'
            f'Автор: {pr.author}\n'
            f'Ветка: {pr.base_branch}\n\n'
            f'Diff:\n{pr.diff}'
        )

        return self._chat(system, user, max_tokens=800)
