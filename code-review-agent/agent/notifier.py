"""
notifier.py — публикация ревью в GitHub Pull Request
В отличие от других агентов, вывод идёт не на email, а прямо в GitHub.
"""

import logging

import requests

from configs.config import Config
from agent.tools import PullRequest, GITHUB_API_URL

logger = logging.getLogger(__name__)

# Метка агента в тексте ревью — чтобы отличать автоматические ревью от ручных
_REVIEW_FOOTER = '\n\n---\n*Автоматическое ревью от агента ИИ-Синтез*'


class GitHubNotifier:
    """
    Публикует ревью как комментарий к Pull Request через GitHub API.
    Агент вызывает post_review() как последний шаг цикла для каждого PR.
    """

    def __init__(self, config: Config):
        self.repo = config.github_repo
        self._headers = {
            'Authorization': f'token {config.github_token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        }

    def post_review(self, pr: PullRequest) -> bool:
        """
        Публикует ревью как PR review с типом COMMENT.
        Возвращает True если ревью опубликовано успешно.
        """
        if not pr.review:
            logger.warning(f'PR #{pr.number}: ревью пустое — пропускаем публикацию.')
            return False

        body = pr.review + _REVIEW_FOOTER

        try:
            response = requests.post(
                f'{GITHUB_API_URL}/repos/{self.repo}/pulls/{pr.number}/reviews',
                headers=self._headers,
                json={
                    'commit_id': pr.head_sha,
                    'body': body,
                    'event': 'COMMENT',  # не меняем статус PR, только добавляем комментарий
                },
                timeout=15,
            )
            response.raise_for_status()
            logger.info(f'PR #{pr.number}: ревью опубликовано → {pr.url}')
            return True
        except requests.HTTPError as e:
            logger.error(f'GitHub API ошибка при публикации ревью PR #{pr.number} (HTTP {e.response.status_code}): {e.response.text}')
            return False
        except Exception as e:
            logger.error(f'Ошибка при публикации ревью PR #{pr.number}: {e}')
            return False
