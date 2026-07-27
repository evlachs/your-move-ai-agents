"""
scanner.py — инструмент для построения «карты проекта»
Обходит дерево целевого репозитория через GitHub API и извлекает
структуру кода (docstring'и, классы, функции) без полных тел функций —
это держит объём контекста для YandexGPT в разумных пределах.
"""

import ast
import logging

logger = logging.getLogger(__name__)

# Каталоги, которые не несут пользу для документации проекта
EXCLUDED_DIRS = {
    '.git', '__pycache__', 'venv', '.venv', 'node_modules',
    '.idea', '.vscode', 'data', 'dist', 'build', '.pytest_cache',
}

# Файлы, чьё содержимое целиком полезно для документации (они короткие)
CONTEXT_FILES = {
    'requirements.txt', 'Dockerfile', 'package.json', 'pyproject.toml',
    'env.example', '.env.example', 'docker-compose.yml', 'docker-compose.yaml',
}

MAX_FILE_SIZE = 50_000  # байт — файлы крупнее пропускаем, чтобы не раздувать контекст


class ProjectScanner:
    """
    Строит текстовую карту проекта: дерево файлов + извлечённые сигнатуры.
    Работает напрямую с GitHub API (через GitHubTool), без локального клонирования.
    """

    def __init__(self, github_tool):
        self.github = github_tool

    def build_project_map(self, ref: str) -> str:
        """
        Возвращает компактное текстовое описание проекта:
        дерево файлов + docstring'и/сигнатуры из .py файлов +
        содержимое значимых конфигурационных файлов.
        """
        paths = self._walk(ref)
        logger.info(f'Сканер: найдено {len(paths)} файлов для анализа')

        tree_section = '\n'.join(sorted(paths))

        symbol_sections = []
        config_sections = []

        for path in sorted(paths):
            is_python = path.endswith('.py')
            is_context = path.split('/')[-1] in CONTEXT_FILES
            if not is_python and not is_context:
                continue

            content = self.github.get_file_content(path, ref)
            if content is None:
                continue

            if is_python:
                summary = self._summarize_python(path, content)
                if summary:
                    symbol_sections.append(summary)
            else:
                config_sections.append(f'### {path}\n```\n{content}\n```')

        parts = [
            '## Дерево файлов\n```\n' + tree_section + '\n```',
        ]
        if symbol_sections:
            parts.append('## Структура кода (Python)\n\n' + '\n\n'.join(symbol_sections))
        if config_sections:
            parts.append('## Конфигурационные файлы\n\n' + '\n\n'.join(config_sections))

        return '\n\n'.join(parts)

    def _walk(self, ref: str) -> list[str]:
        """Рекурсивно собирает пути всех файлов репозитория, пропуская служебные каталоги."""
        result = []
        stack = ['']

        while stack:
            current = stack.pop()
            for item in self.github.list_directory(current, ref):
                if item.type == 'dir':
                    if item.name not in EXCLUDED_DIRS:
                        stack.append(item.path)
                else:
                    if item.size <= MAX_FILE_SIZE:
                        result.append(item.path)

        return result

    def _summarize_python(self, path: str, content: str) -> str | None:
        """
        Извлекает из .py файла: docstring модуля, классы (с docstring'ами и
        методами), функции верхнего уровня — без тел. Возвращает None если
        файл не парсится (например, синтаксическая ошибка в исходнике).
        """
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            logger.warning(f'Сканер: не удалось разобрать {path}: {e}')
            return None

        lines = [f'### {path}']

        module_doc = ast.get_docstring(tree)
        if module_doc:
            lines.append(module_doc.strip())

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                lines.append(f'- class {node.name}{self._bases(node)}:')
                doc = ast.get_docstring(node)
                if doc:
                    lines.append(f'    """{doc.strip()}"""')
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        lines.append(f'    - def {sub.name}{self._signature(sub)}')

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                lines.append(f'- def {node.name}{self._signature(node)}')
                doc = ast.get_docstring(node)
                if doc:
                    lines.append(f'    """{doc.strip()}"""')

        return '\n'.join(lines)

    @staticmethod
    def _bases(node: ast.ClassDef) -> str:
        names = [ast.unparse(base) for base in node.bases]
        return f'({", ".join(names)})' if names else ''

    @staticmethod
    def _signature(node) -> str:
        try:
            return f'({ast.unparse(node.args)})'
        except Exception:
            return '(...)'
