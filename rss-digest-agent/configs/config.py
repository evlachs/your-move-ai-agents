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
    # --- RSS-ленты ---
    rss_feeds: list[str]         # список URL-адресов лент
    max_entries_per_feed: int    # сколько последних записей брать из каждой ленты

    # --- Тематический контекст для YandexGPT ---
    digest_topics: str           # например: "Python, ИИ, стартапы" — или пустая строка

    # --- YandexGPT ---
    yandex_api_key: str
    yandex_folder_id: str
    yandex_gpt_model: str

    # --- SMTP (доставка дайджеста) ---
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

    raw_feeds = require('RSS_FEEDS')
    feeds = [url.strip() for url in raw_feeds.split(';') if url.strip()]
    if not feeds:
        raise EnvironmentError('RSS_FEEDS не содержит ни одного URL')

    return Config(
        rss_feeds=feeds,
        max_entries_per_feed=int(os.getenv('MAX_ENTRIES_PER_FEED', '20')),

        digest_topics=os.getenv('DIGEST_TOPICS', ''),

        yandex_api_key=require('YANDEX_API_KEY'),
        yandex_folder_id=require('YANDEX_FOLDER_ID'),
        yandex_gpt_model=os.getenv('YANDEX_GPT_MODEL', 'yandexgpt-lite'),

        smtp_host=os.getenv('SMTP_HOST', 'smtp.yandex.ru'),
        smtp_port=int(os.getenv('SMTP_PORT', '465')),
        smtp_user=require('SMTP_USER'),
        smtp_password=require('SMTP_PASSWORD'),
        email_from=os.getenv('EMAIL_FROM', os.getenv('SMTP_USER', '')),
        email_to=require('EMAIL_TO'),

        db_path=os.getenv('DB_PATH', 'data/agent_memory.db'),

        digest_hour=int(os.getenv('DIGEST_HOUR', '9')),
        digest_minute=int(os.getenv('DIGEST_MINUTE', '0')),
        timezone=os.getenv('TIMEZONE', 'Europe/Moscow'),
    )
