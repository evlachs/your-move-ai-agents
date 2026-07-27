"""
tools.py — инструменты агента
HHApiTool     : поиск вакансий через публичный API HH.ru.
YandexGPTTool : анализ вакансии — оценка интереса и ключевые требования.
"""

import logging
import re
from dataclasses import dataclass, field

import requests

from configs.config import Config

logger = logging.getLogger(__name__)

HH_API_URL = 'https://api.hh.ru/vacancies'
YANDEX_GPT_URL = 'https://llm.api.cloud.yandex.net/foundationModels/v1/completion'


@dataclass
class Vacancy:
    id: str
    title: str
    employer: str
    area: str
    salary_from: int | None
    salary_to: int | None
    salary_currency: str
    url: str
    requirement: str
    responsibility: str
    # Заполняется YandexGPT после первичной загрузки
    assessment: str = ''       # 'интересная' | 'средняя' | 'не подходит'
    key_points: list[str] = field(default_factory=list)

    def salary_str(self) -> str:
        """Форматирует зарплату в читаемую строку."""
        if self.salary_from is None and self.salary_to is None:
            return 'не указана'
        parts = []
        if self.salary_from is not None:
            parts.append(f'от {self.salary_from:,}')
        if self.salary_to is not None:
            parts.append(f'до {self.salary_to:,}')
        return f'{" ".join(parts)} {self.salary_currency}'


# --- Инструмент 1: HH.ru API ---

class HHApiTool:
    """
    Инструмент для поиска вакансий через публичный API HH.ru.
    Авторизация не требуется для базового поиска.
    """

    # Заголовок обязателен по правилам API HH.ru
    _HEADERS = {'User-Agent': 'vacancy-tracker-agent/1.0 (educational project)'}

    def __init__(self, config: Config):
        self.config = config

    def search(self) -> list[Vacancy]:
        """
        Выполняет поиск вакансий по параметрам из конфига.
        Возвращает список вакансий, отсортированных по дате публикации (новые первыми).
        """
        params = {
            'text': self.config.hh_search_text,
            'area': self.config.hh_area_id,
            'order_by': 'publication_time',
            'per_page': self.config.hh_per_page,
            'page': 0,
        }
        if self.config.hh_salary_from > 0:
            params['salary'] = self.config.hh_salary_from
        if self.config.hh_only_with_salary:
            params['only_with_salary'] = 'true'
        if self.config.hh_experience:
            params['experience'] = self.config.hh_experience
        if self.config.hh_employment:
            params['employment'] = self.config.hh_employment

        try:
            response = requests.get(
                HH_API_URL,
                params=params,
                headers=self._HEADERS,
                timeout=15,
            )
            response.raise_for_status()
            items = response.json().get('items', [])
        except requests.HTTPError as e:
            logger.error(f'HH.ru API ошибка (HTTP {e.response.status_code}): {e.response.text}')
            return []
        except Exception as e:
            logger.error(f'HH.ru API ошибка: {e}')
            return []

        vacancies = [self._parse(item) for item in items]
        logger.info(f'HH.ru: получено {len(vacancies)} вакансий по запросу "{self.config.hh_search_text}".')
        return vacancies

    @staticmethod
    def _parse(item: dict) -> Vacancy:
        """Разбирает один элемент ответа HH.ru API в объект Vacancy."""
        salary = item.get('salary') or {}
        snippet = item.get('snippet') or {}

        # HH.ru возвращает теги <highlighttext> в сниппетах — убираем их
        def clean(text: str | None) -> str:
            if not text:
                return ''
            return re.sub(r'<[^>]+>', '', text).strip()

        return Vacancy(
            id=str(item['id']),
            title=item.get('name', ''),
            employer=(item.get('employer') or {}).get('name', ''),
            area=(item.get('area') or {}).get('name', ''),
            salary_from=salary.get('from'),
            salary_to=salary.get('to'),
            salary_currency=salary.get('currency', ''),
            url=item.get('alternate_url', ''),
            requirement=clean(snippet.get('requirement')),
            responsibility=clean(snippet.get('responsibility')),
        )


# --- Инструмент 2: YandexGPT ---

class YandexGPTTool:
    """Инструмент для анализа вакансий через YandexGPT."""

    def __init__(self, config: Config):
        self.api_key = config.yandex_api_key
        self.folder_id = config.yandex_folder_id
        self.model = config.yandex_gpt_model
        self.candidate_profile = config.candidate_profile

    def _chat(self, system: str, user: str, max_tokens: int = 300) -> str:
        try:
            response = requests.post(
                YANDEX_GPT_URL,
                headers={
                    'Authorization': f'Api-Key {self.api_key}',
                    'x-folder-id': self.folder_id,
                },
                json={
                    'modelUri': f'gpt://{self.folder_id}/{self.model}',
                    'completionOptions': {
                        'temperature': 0.2,
                        'maxTokens': max_tokens,
                    },
                    'messages': [
                        {'role': 'system', 'text': system},
                        {'role': 'user', 'text': user},
                    ],
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()['result']['alternatives'][0]['message']['text'].strip()
        except requests.HTTPError as e:
            logger.error(f'YandexGPT ошибка (HTTP {e.response.status_code}): {e.response.text}')
            return ''
        except Exception as e:
            logger.error(f'YandexGPT ошибка: {e}')
            return ''

    def analyze_vacancy(self, vacancy: Vacancy) -> tuple[str, list[str]]:
        """
        Оценивает вакансию с точки зрения соискателя.
        Возвращает (оценка, список ключевых требований).
        Оценка: 'интересная' | 'средняя' | 'не подходит'.
        """
        profile_block = f'Профиль соискателя: {self.candidate_profile}\n\n' if self.candidate_profile else ''

        system = (
            'Ты помощник, который оценивает вакансии для соискателя. '
            'Ответь СТРОГО в следующем формате, без лишнего текста:\n'
            'ОЦЕНКА: интересная|средняя|не подходит\n'
            'ТРЕБОВАНИЯ:\n'
            '- первое требование\n'
            '- второе требование\n'
            '(не более 4 пунктов; если требования не указаны — напиши "- не указаны")'
        )
        user = (
            f'{profile_block}'
            f'Вакансия: {vacancy.title}\n'
            f'Работодатель: {vacancy.employer}\n'
            f'Зарплата: {vacancy.salary_str()}\n'
            f'Требования: {vacancy.requirement or "не указаны"}\n'
            f'Обязанности: {vacancy.responsibility or "не указаны"}'
        )

        raw = self._chat(system, user, max_tokens=250)
        return self._parse_analysis(raw)

    @staticmethod
    def _parse_analysis(raw: str) -> tuple[str, list[str]]:
        assessment = 'средняя'
        key_points: list[str] = []

        assessment_match = re.search(r'ОЦЕНКА:\s*(интересная|средняя|не подходит)', raw, re.IGNORECASE)
        points_match = re.search(r'ТРЕБОВАНИЯ:\s*(.+)', raw, re.DOTALL | re.IGNORECASE)

        if assessment_match:
            assessment = assessment_match.group(1).lower()

        if points_match:
            for line in points_match.group(1).splitlines():
                line = line.strip().lstrip('-•*').strip()
                if line and line.lower() != 'не указаны':
                    key_points.append(line)

        return assessment, key_points
