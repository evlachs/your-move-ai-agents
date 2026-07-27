"""
config.py — все настройки агента в одном месте
Читает из переменных окружения (.env файл для локальной разработки)
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # --- GitHub ---
    github_token: str      # Personal Access Token с правами repo
    github_repo: str       # формат: owner/repo, например "myorg/backend"
    github_base_branch: str  # ревьюим только PR в эту ветку; пусто = все PR

    # --- Ограничения diff ---
    max_diff_chars: int    # сколько символов diff передаём в GPT (слишком большой diff = плохое ревью)

    # --- YandexGPT ---
    yandex_api_key: str
    yandex_folder_id: str
    yandex_gpt_model: str

    # --- База данных ---
    db_path: str

    # --- Расписание ---
    check_interval_hours: int
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
        github_repo=require('GITHUB_REPO'),
        github_base_branch=os.getenv('GITHUB_BASE_BRANCH', ''),

        max_diff_chars=int(os.getenv('MAX_DIFF_CHARS', '8000')),

        yandex_api_key=require('YANDEX_API_KEY'),
        yandex_folder_id=require('YANDEX_FOLDER_ID'),
        yandex_gpt_model=os.getenv('YANDEX_GPT_MODEL', 'yandexgpt'),

        db_path=os.getenv('DB_PATH', 'data/agent_memory.db'),

        check_interval_hours=int(os.getenv('CHECK_INTERVAL_HOURS', '1')),
        timezone=os.getenv('TIMEZONE', 'Europe/Moscow'),
    )
