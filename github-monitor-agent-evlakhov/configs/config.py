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
    # --- GitHub ---
    github_token: str       # Personal Access Token
    github_repo: str        # например 'torvalds/linux'
    github_branch: str

    # --- YandexGPT ---
    yandex_api_key: str     # IAM-токен или API-ключ
    yandex_folder_id: str   # ID каталога в Яндекс Клауд

    # --- Email ---
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_from: str
    email_to: str           # получатель дайджеста

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
        github_repo=require('GITHUB_REPO'),
        github_branch=os.getenv('GITHUB_BRANCH', 'main'),

        yandex_api_key=require('YANDEX_API_KEY'),
        yandex_folder_id=require('YANDEX_FOLDER_ID'),

        smtp_host=os.getenv('SMTP_HOST', 'smtp.yandex.ru'),
        smtp_port=int(os.getenv('SMTP_PORT', '465')),
        smtp_user=require('SMTP_USER'),
        smtp_password=require('SMTP_PASSWORD'),
        email_from=os.getenv('EMAIL_FROM', os.getenv('SMTP_USER', '')),
        email_to=require('EMAIL_TO'),

        db_path=os.getenv('DB_PATH', '../databases/agent_memory.db'),

        schedule_hour=int(os.getenv('SCHEDULE_HOUR', '9')),
        schedule_minute=int(os.getenv('SCHEDULE_MINUTE', '0')),
        timezone=os.getenv('TIMEZONE', 'Europe/Moscow'),
    )
