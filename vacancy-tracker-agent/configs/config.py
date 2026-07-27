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
    # --- Фильтры поиска HH.ru ---
    hh_search_text: str      # ключевые слова, например "Python разработчик"
    hh_area_id: str          # ID региона: 1 = Москва, 2 = Санкт-Петербург, 113 = вся Россия
    hh_salary_from: int      # минимальная зарплата (0 = без ограничения)
    hh_only_with_salary: bool
    hh_experience: str       # noExperience | between1And3 | between3And6 | moreThan6
    hh_employment: str       # full | part | project | (пустая строка = любой)
    hh_per_page: int         # сколько вакансий брать за один запрос (макс. 100)

    # --- Профиль соискателя (контекст для YandexGPT) ---
    candidate_profile: str   # краткое описание: кто ищет и что важно

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
        hh_search_text=require('HH_SEARCH_TEXT'),
        hh_area_id=os.getenv('HH_AREA_ID', '113'),
        hh_salary_from=int(os.getenv('HH_SALARY_FROM', '0')),
        hh_only_with_salary=os.getenv('HH_ONLY_WITH_SALARY', 'false').lower() == 'true',
        hh_experience=os.getenv('HH_EXPERIENCE', ''),
        hh_employment=os.getenv('HH_EMPLOYMENT', ''),
        hh_per_page=int(os.getenv('HH_PER_PAGE', '50')),

        candidate_profile=os.getenv('CANDIDATE_PROFILE', ''),

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

        check_interval_hours=int(os.getenv('CHECK_INTERVAL_HOURS', '4')),
        timezone=os.getenv('TIMEZONE', 'Europe/Moscow'),
    )
