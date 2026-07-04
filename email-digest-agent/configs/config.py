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
    # --- IMAP (рабочая почта, которую агент проверяет) ---
    imap_host: str
    imap_port: int
    imap_user: str
    imap_password: str
    imap_mailbox: str

    # --- YandexGPT ---
    yandex_api_key: str
    yandex_folder_id: str

    # --- SMTP (доставка дайджеста) ---
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_from: str
    email_to: str

    # --- База данных ---
    db_path: str

    # --- Расписание: два запуска в день ---
    lunch_hour: int
    lunch_minute: int
    evening_hour: int
    evening_minute: int
    timezone: str


def load_config() -> Config:
    """Загружает конфиг из переменных окружения. Падает если что-то не задано."""

    def require(key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise EnvironmentError(f'Переменная окружения {key!r} не задана')
        return value

    return Config(
        imap_host=os.getenv('IMAP_HOST', 'imap.yandex.ru'),
        imap_port=int(os.getenv('IMAP_PORT', '993')),
        imap_user=require('IMAP_USER'),
        imap_password=require('IMAP_PASSWORD'),
        imap_mailbox=os.getenv('IMAP_MAILBOX', 'INBOX'),

        yandex_api_key=require('YANDEX_API_KEY'),
        yandex_folder_id=require('YANDEX_FOLDER_ID'),

        smtp_host=os.getenv('SMTP_HOST', 'smtp.yandex.ru'),
        smtp_port=int(os.getenv('SMTP_PORT', '465')),
        smtp_user=require('SMTP_USER'),
        smtp_password=require('SMTP_PASSWORD'),
        email_from=os.getenv('EMAIL_FROM', os.getenv('SMTP_USER', '')),
        email_to=require('EMAIL_TO'),

        db_path=os.getenv('DB_PATH', 'data/agent_memory.db'),

        lunch_hour=int(os.getenv('LUNCH_HOUR', '13')),
        lunch_minute=int(os.getenv('LUNCH_MINUTE', '0')),
        evening_hour=int(os.getenv('EVENING_HOUR', '18')),
        evening_minute=int(os.getenv('EVENING_MINUTE', '0')),
        timezone=os.getenv('TIMEZONE', 'Europe/Moscow'),
    )
