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
    # --- Источник данных: Google Sheets CSV-экспорт ---
    sheets_csv_url: str     # URL вида: https://docs.google.com/spreadsheets/d/.../export?format=csv
    text_column: str        # название колонки с текстом отзыва
    id_column: str          # название колонки с уникальным ID; пусто = хэш текста

    # --- Ограничения ---
    max_reviews_per_run: int  # сколько новых отзывов обрабатывать за один запуск

    # --- YandexGPT ---
    yandex_api_key: str
    yandex_folder_id: str
    yandex_gpt_model: str

    # --- SMTP (доставка отчёта) ---
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_from: str
    email_to: str

    # --- База данных ---
    db_path: str

    # --- Расписание: один раз в день ---
    digest_hour: int
    digest_minute: int
    timezone: str


def load_config() -> Config:
    """Загружает конфиг из переменных окружения. Падает если что-то не задано."""

    def require(key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise EnvironmentError(f'Переменная окружения {key!r} не задана')
        return value

    smtp_user = require('SMTP_USER')

    return Config(
        sheets_csv_url=require('SHEETS_CSV_URL'),
        text_column=os.getenv('TEXT_COLUMN', 'Отзыв'),
        id_column=os.getenv('ID_COLUMN', ''),

        max_reviews_per_run=int(os.getenv('MAX_REVIEWS_PER_RUN', '50')),

        yandex_api_key=require('YANDEX_API_KEY'),
        yandex_folder_id=require('YANDEX_FOLDER_ID'),
        yandex_gpt_model=os.getenv('YANDEX_GPT_MODEL', 'yandexgpt-lite'),

        smtp_host=os.getenv('SMTP_HOST', 'smtp.yandex.ru'),
        smtp_port=int(os.getenv('SMTP_PORT', '465')),
        smtp_user=smtp_user,
        smtp_password=require('SMTP_PASSWORD'),
        email_from=os.getenv('EMAIL_FROM', smtp_user),
        email_to=require('EMAIL_TO'),

        db_path=os.getenv('DB_PATH', 'data/agent_memory.db'),

        digest_hour=int(os.getenv('DIGEST_HOUR', '9')),
        digest_minute=int(os.getenv('DIGEST_MINUTE', '0')),
        timezone=os.getenv('TIMEZONE', 'Europe/Moscow'),
    )
