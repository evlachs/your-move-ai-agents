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
    # --- YandexGPT / YandexART ---
    yandex_api_key: str     # IAM-токен или API-ключ
    yandex_folder_id: str   # ID каталога в Яндекс Клауд

    # --- VK ---
    vk_access_token: str    # ключ доступа сообщества (права wall, photos)
    vk_group_id: str        # ID сообщества (число, без минуса)

    # --- Публикация ---
    publish_hour: int       # час, на который ставится отложенная запись

    # --- База данных ---
    db_path: str            # путь к файлу SQLite

    # --- Расписание запуска агента ---
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
        yandex_api_key=require('YANDEX_API_KEY'),
        yandex_folder_id=require('YANDEX_FOLDER_ID'),

        vk_access_token=require('VK_ACCESS_TOKEN'),
        vk_group_id=require('VK_GROUP_ID'),

        publish_hour=int(os.getenv('PUBLISH_HOUR', '12')),

        db_path=os.getenv('DB_PATH', 'data/agent_memory.db'),

        schedule_hour=int(os.getenv('SCHEDULE_HOUR', '9')),
        schedule_minute=int(os.getenv('SCHEDULE_MINUTE', '0')),
        timezone=os.getenv('TIMEZONE', 'Europe/Moscow'),
    )
