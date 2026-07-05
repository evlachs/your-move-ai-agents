"""
tools.py — инструменты агента
GitHub API: читаем дерево репозитория, сравниваем коммиты, открываем PR.
YandexGPT: генерируем README, документацию и описание PR.
"""

import logging

import requests
from github import Github, GithubException, UnknownObjectException

from configs.config import Config


logger = logging.getLogger(__name__)


# --- Инструмент 1: GitHub API ---

class GitHubTool:
    """
    Инструмент для работы с целевым репозиторием.
    В отличие от read-only мониторинга, этому агенту нужны права на запись:
    создание веток, коммитов и Pull Request'ов.
    """

    def __init__(self, config: Config):
        self.github = Github(config.github_token)
        self.repo_name = config.target_repo
        self.target_branch = config.target_branch
        self._repo = None

    @property
    def repo(self):
        """Ленивая загрузка репозитория — один раз при первом обращении."""
        if self._repo is None:
            self._repo = self.github.get_repo(self.repo_name)
        return self._repo

    def get_head_sha(self) -> str:
        """SHA последнего коммита в целевой ветке."""
        return self.repo.get_branch(self.target_branch).commit.sha

    def list_directory(self, path: str, ref: str) -> list:
        """
        Список содержимого каталога (файлы и подкаталоги).
        Каждый элемент имеет .type ('file'/'dir'), .name, .path, .size.
        """
        try:
            contents = self.repo.get_contents(path or '', ref=ref)
        except GithubException as e:
            logger.error(f'Ошибка GitHub API при чтении {path!r}: {e}')
            return []
        return contents if isinstance(contents, list) else [contents]

    def get_file_content(self, path: str, ref: str) -> str | None:
        """Текстовое содержимое файла. None если файл не текстовый или не найден."""
        try:
            content_file = self.repo.get_contents(path, ref=ref)
            return content_file.decoded_content.decode('utf-8')
        except UnicodeDecodeError:
            return None
        except GithubException as e:
            logger.warning(f'Не удалось прочитать {path!r}: {e}')
            return None

    def compare_commits(self, base_sha: str, head_sha: str) -> list[str]:
        """Список путей файлов, изменённых между двумя коммитами."""
        try:
            comparison = self.repo.compare(base_sha, head_sha)
            return [f.filename for f in comparison.files]
        except GithubException as e:
            logger.error(f'Ошибка GitHub API при сравнении коммитов: {e}')
            return []

    def create_branch(self, branch_name: str, from_sha: str):
        """Создаёт новую ветку от указанного коммита."""
        self.repo.create_git_ref(ref=f'refs/heads/{branch_name}', sha=from_sha)

    def commit_file(self, branch: str, path: str, content: str, message: str):
        """Создаёт или обновляет файл в ветке (одним коммитом)."""
        try:
            existing = self.repo.get_contents(path, ref=branch)
            self.repo.update_file(path, message, content, existing.sha, branch=branch)
        except UnknownObjectException:
            self.repo.create_file(path, message, content, branch=branch)

    def open_pull_request(self, branch: str, title: str, body: str) -> str:
        """Открывает Pull Request из ветки в целевую ветку. Возвращает URL PR."""
        pr = self.repo.create_pull(
            title=title,
            body=body,
            head=branch,
            base=self.target_branch,
        )
        return pr.html_url


# --- Инструмент 2: YandexGPT ---

class YandexGPTTool:
    """
    Инструмент для генерации документации через YandexGPT.
    Используем Pro-модель (yandexgpt) — генерация README и документации
    требует более развёрнутых и связных текстов, чем короткий анализ PR.
    """

    MODEL_PRO = 'yandexgpt'

    def __init__(self, config: Config):
        self.config = config
        self.folder_id = config.yandex_folder_id

    def _chat(self, system: str, user: str, max_tokens: int = 2000) -> str:
        try:
            response = requests.post(
                'https://llm.api.cloud.yandex.net/foundationModels/v1/completion',
                headers={
                    'Authorization': f'Api-Key {self.config.yandex_api_key}',
                    'x-folder-id': self.folder_id,
                },
                json={
                    'modelUri': f'gpt://{self.folder_id}/{self.MODEL_PRO}',
                    'completionOptions': {
                        'temperature': 0.3,
                        'maxTokens': max_tokens,
                    },
                    'messages': [
                        {'role': 'system', 'text': system},
                        {'role': 'user', 'text': user},
                    ],
                },
                timeout=60,
            )
            if not response.ok:
                logger.error(f'YandexGPT ответ: {response.text}')
                response.raise_for_status()
            return response.json()['result']['alternatives'][0]['message']['text']

        except Exception as e:
            logger.error(f'Ошибка YandexGPT: {e}')
            return ''

    def generate_readme(self, project_map: str, existing_readme: str, changed_files: list[str]) -> str:
        """
        Генерирует обновлённый README.md на основе карты проекта.
        Если README уже существует — обновляет его, сохраняя ручные правки
        там, где код не менялся.
        """
        system = (
            'Ты технический писатель. Пишешь README.md для программного проекта. '
            'Отвечай на русском языке, в формате Markdown. '
            'Если передан существующий README — обновляй его, сохраняя структуру '
            'и человеческие формулировки там, где это уместно, но отражай '
            'актуальную структуру и возможности проекта по карте проекта. '
            'Не выдумывай функциональность, которой нет в карте проекта.'
        )
        existing_block = (
            f'Существующий README.md:\n```markdown\n{existing_readme}\n```\n\n'
            if existing_readme else 'README.md в проекте пока нет — напиши с нуля.\n\n'
        )
        changed_block = (
            f'Файлы, изменённые с прошлой генерации: {", ".join(changed_files)}\n\n'
            if changed_files else ''
        )
        user = (
            f'{existing_block}'
            f'{changed_block}'
            f'Карта проекта:\n{project_map}\n\n'
            'Сгенерируй полный текст README.md.'
        )
        return self._chat(system, user, max_tokens=3000)

    def generate_documentation(self, project_map: str, existing_doc: str, changed_files: list[str]) -> str:
        """
        Генерирует подробную документацию проекта: архитектура, установка,
        переменные окружения, описание модулей.
        """
        system = (
            'Ты технический писатель. Пишешь подробную документацию проекта '
            '(DOCUMENTATION.md). Отвечай на русском языке, в формате Markdown. '
            'Структура: 1) Архитектура и принцип работы, 2) Установка и запуск, '
            '3) Переменные окружения, 4) Описание модулей и их назначения. '
            'Если передана существующая документация — обновляй её. '
            'Не выдумывай функциональность, которой нет в карте проекта.'
        )
        existing_block = (
            f'Существующая документация:\n```markdown\n{existing_doc}\n```\n\n'
            if existing_doc else 'Документации пока нет — напиши с нуля.\n\n'
        )
        changed_block = (
            f'Файлы, изменённые с прошлой генерации: {", ".join(changed_files)}\n\n'
            if changed_files else ''
        )
        user = (
            f'{existing_block}'
            f'{changed_block}'
            f'Карта проекта:\n{project_map}\n\n'
            'Сгенерируй полный текст документации.'
        )
        return self._chat(system, user, max_tokens=4000)

    def generate_pr_description(self, repo: str, changed_files: list[str]) -> str:
        """Краткое описание для тела Pull Request."""
        if not changed_files:
            return 'Автоматическое обновление документации (первая генерация).'

        system = 'Ты пишешь краткое описание Pull Request. Markdown, на русском, 3-5 предложений.'
        user = (
            f'Репозиторий {repo}. Автоматически обновлены README.md и документация '
            f'после изменений в файлах: {", ".join(changed_files)}. '
            'Опиши, что было обновлено и почему.'
        )
        return self._chat(system, user, max_tokens=400) or 'Автоматическое обновление документации.'
