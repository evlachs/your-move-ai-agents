"""
config.py — все настройки агента в одном месте
Читает из переменных окружения (.env файл для локальной разработки)
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()  # загружает .env если есть, в продакшне берёт из env контейнера


@dataclass
class Config:
    # --- GitHub (целевой репозиторий, который агент документирует) ---
    github_token: str       # токен с правами на запись (repo: contents + pull requests)
    target_repo: str        # например 'owner/repository-name'
    target_branch: str      # ветка, в которую открывается PR (default branch)

    # --- YandexGPT ---
    yandex_api_key: str     # IAM-токен или API-ключ
    yandex_folder_id: str   # ID каталога в Яндекс Клауд

    # --- Документация ---
    doc_path: str            # путь к подробной документации в целевом репозитории

    # --- База данных ---
    db_path: str            # путь к файлу SQLite

    # --- Расписание ---
    schedule_hour: int
    schedule_minute: int
    timezone: str


def load_config() -> Config:
    """Загружает конфиг из переменных окружения. Падает если что-то не задано."""

    def require(key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise EnvironmentError(f'Переменная окружения {key!r} не задана')
        return value

    return Config(
        github_token=require('GITHUB_TOKEN'),
        target_repo=require('TARGET_REPO'),
        target_branch=os.getenv('TARGET_BRANCH', 'main'),

        yandex_api_key=require('YANDEX_API_KEY'),
        yandex_folder_id=require('YANDEX_FOLDER_ID'),

        doc_path=os.getenv('DOC_PATH', 'docs/DOCUMENTATION.md'),

        db_path=os.getenv('DB_PATH', 'data/agent_memory.db'),

        schedule_hour=int(os.getenv('SCHEDULE_HOUR', '9')),
        schedule_minute=int(os.getenv('SCHEDULE_MINUTE', '0')),
        timezone=os.getenv('TIMEZONE', 'Europe/Moscow'),
    )
