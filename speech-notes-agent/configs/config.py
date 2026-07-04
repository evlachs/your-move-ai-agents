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
    # --- Папка с аудиозаписями ---
    audio_dir: str
    audio_extensions: list[str]

    # --- Yandex SpeechKit ---
    yandex_api_key: str
    yandex_folder_id: str
    speechkit_language: str
    speechkit_model: str
    speechkit_poll_interval: int   # секунд между проверками статуса операции
    speechkit_max_polls: int       # максимум проверок (max_polls * poll_interval = таймаут)

    # --- YandexGPT ---
    yandex_gpt_model: str

    # --- SMTP (доставка заметок) ---
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

    raw_extensions = os.getenv('AUDIO_EXTENSIONS', '.mp3,.ogg,.wav,.m4a')
    extensions = [e.strip().lower() for e in raw_extensions.split(',') if e.strip()]

    return Config(
        audio_dir=os.getenv('AUDIO_DIR', 'audio'),
        audio_extensions=extensions,

        yandex_api_key=require('YANDEX_API_KEY'),
        yandex_folder_id=require('YANDEX_FOLDER_ID'),
        speechkit_language=os.getenv('SPEECHKIT_LANGUAGE', 'ru-RU'),
        speechkit_model=os.getenv('SPEECHKIT_MODEL', 'general'),
        speechkit_poll_interval=int(os.getenv('SPEECHKIT_POLL_INTERVAL', '10')),
        speechkit_max_polls=int(os.getenv('SPEECHKIT_MAX_POLLS', '60')),

        yandex_gpt_model=os.getenv('YANDEX_GPT_MODEL', 'yandexgpt-lite'),

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
