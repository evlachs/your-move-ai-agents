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
    # --- Yandex Cloud Logging ---
    yc_iam_token: str   # IAM-токен: yc iam create-token (живёт ~12 часов, обновлять вручную)
    log_group_id: str   # ID группы логов в Yandex Cloud Logging

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
        yc_iam_token=require('YC_IAM_TOKEN'),
        log_group_id=require('LOG_GROUP_ID'),

        yandex_api_key=require('YANDEX_API_KEY'),
        yandex_folder_id=require('YANDEX_FOLDER_ID'),

        smtp_host=os.getenv('SMTP_HOST', 'smtp.yandex.ru'),
        smtp_port=int(os.getenv('SMTP_PORT', '465')),
        smtp_user=require('SMTP_USER'),
        smtp_password=require('SMTP_PASSWORD'),
        email_from=os.getenv('EMAIL_FROM', os.getenv('SMTP_USER', '')),
        email_to=require('EMAIL_TO'),

        db_path=os.getenv('DB_PATH', 'data/agent_memory.db'),

        check_interval_hours=int(os.getenv('CHECK_INTERVAL_HOURS', '1')),
        timezone=os.getenv('TIMEZONE', 'Europe/Moscow'),
    )
