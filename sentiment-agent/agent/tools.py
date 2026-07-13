"""
tools.py — инструменты агента
SheetsFetcherTool : загружает отзывы из Google Sheets через CSV-экспорт.
YandexGPTTool     : определяет тональность каждого отзыва и генерирует итоговый отчёт.
"""

import csv
import hashlib
import io
import logging
import re
from dataclasses import dataclass, field

import requests

from configs.config import Config

logger = logging.getLogger(__name__)

YANDEX_GPT_URL = 'https://llm.api.cloud.yandex.net/foundationModels/v1/completion'


@dataclass
class Review:
    id: str               # уникальный идентификатор (из колонки или хэш текста)
    text: str             # исходный текст отзыва
    sentiment: str = ''   # 'позитивный' | 'нейтральный' | 'негативный'
    topics: list[str] = field(default_factory=list)


# --- Инструмент 1: Google Sheets ---

class SheetsFetcherTool:
    """
    Инструмент для загрузки отзывов из Google Sheets.
    Агент вызывает его чтобы получить список новых отзывов.

    Таблица должна быть публичной (Файл → Поделиться → Все, у кого есть ссылка).
    URL для экспорта: Файл → Поделиться → Опубликовать в интернете → CSV.
    """

    def __init__(self, config: Config):
        self.csv_url = config.sheets_csv_url
        self.text_column = config.text_column
        self.id_column = config.id_column
        self.max_reviews = config.max_reviews_per_run

    def fetch(self) -> list[Review]:
        """
        Скачивает CSV и возвращает список отзывов.
        Порядок: самые новые записи — в конце файла (так добавляет Google Forms).
        """
        try:
            response = requests.get(self.csv_url, timeout=15)
            response.raise_for_status()
        except requests.HTTPError as e:
            logger.error(f'Sheets: ошибка загрузки (HTTP {e.response.status_code}): {e.response.text}')
            return []
        except Exception as e:
            logger.error(f'Sheets: ошибка загрузки: {e}')
            return []

        # Google Sheets может добавлять UTF-8 BOM — убираем его
        content = response.content.decode('utf-8-sig')
        return self._parse_csv(content)

    def _parse_csv(self, content: str) -> list[Review]:
        reader = csv.DictReader(io.StringIO(content))

        if self.text_column not in (reader.fieldnames or []):
            logger.error(
                f'Sheets: колонка "{self.text_column}" не найдена. '
                f'Доступные колонки: {reader.fieldnames}'
            )
            return []

        reviews = []
        for row in reader:
            text = row.get(self.text_column, '').strip()
            if not text:
                continue

            review_id = self._make_id(row, text)
            reviews.append(Review(id=review_id, text=text))

        logger.info(f'Sheets: загружено {len(reviews)} отзывов.')
        return reviews

    def _make_id(self, row: dict, text: str) -> str:
        """Возвращает ID из колонки конфига или MD5-хэш текста."""
        if self.id_column and row.get(self.id_column):
            return str(row[self.id_column]).strip()
        return hashlib.md5(text.encode('utf-8')).hexdigest()


# --- Инструмент 2: YandexGPT ---

class YandexGPTTool:
    """Инструмент для анализа тональности отзывов через YandexGPT."""

    _MAX_TEXT_LEN = 1000   # символов текста отзыва — обрезаем длинные
    _SUMMARY_SAMPLE = 30   # сколько отзывов передаём для итогового резюме

    def __init__(self, config: Config):
        self.api_key = config.yandex_api_key
        self.folder_id = config.yandex_folder_id
        self.model = config.yandex_gpt_model

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

    def analyze_review(self, review: Review) -> tuple[str, list[str]]:
        """
        Определяет тональность отзыва и выделяет ключевые темы.
        Возвращает (тональность, темы).
        Тональность: 'позитивный' | 'нейтральный' | 'негативный'.
        """
        system = (
            'Ты аналитик отзывов. Ответь СТРОГО в следующем формате, без лишнего текста:\n'
            'ТОНАЛЬНОСТЬ: позитивный|нейтральный|негативный\n'
            'ТЕМЫ:\n'
            '- первая тема\n'
            '- вторая тема\n'
            '(не более 3 пунктов; если тем нет — напиши "- нет")'
        )
        text = review.text[: self._MAX_TEXT_LEN]
        raw = self._chat(system, f'Отзыв: {text}', max_tokens=150)
        return self._parse_analysis(raw)

    def generate_summary(self, reviews: list[Review]) -> str:
        """
        Генерирует итоговый абзац-резюме по всей выборке отзывов.
        Передаёт в GPT не более _SUMMARY_SAMPLE отзывов чтобы не переполнить контекст.
        """
        sample = reviews[: self._SUMMARY_SAMPLE]
        lines = [f'[{r.sentiment or "?"}] {r.text[:200]}' for r in sample]
        block = '\n'.join(lines)

        neg_count = sum(1 for r in reviews if r.sentiment == 'негативный')
        pos_count = sum(1 for r in reviews if r.sentiment == 'позитивный')

        system = (
            'Ты аналитик обратной связи. Напиши краткое резюме (3-5 предложений) на русском языке: '
            'общее настроение, главные темы и проблемы, конкретные рекомендации если есть. '
            'Опирайся только на данные из отзывов.'
        )
        user = (
            f'Всего новых отзывов: {len(reviews)}. '
            f'Позитивных: {pos_count}, негативных: {neg_count}.\n\n'
            f'Выборка отзывов:\n{block}'
        )
        return self._chat(system, user, max_tokens=300)

    @staticmethod
    def _parse_analysis(raw: str) -> tuple[str, list[str]]:
        sentiment = 'нейтральный'
        topics: list[str] = []

        sentiment_match = re.search(r'ТОНАЛЬНОСТЬ:\s*(позитивный|нейтральный|негативный)', raw, re.IGNORECASE)
        topics_match = re.search(r'ТЕМЫ:\s*(.+)', raw, re.DOTALL | re.IGNORECASE)

        if sentiment_match:
            sentiment = sentiment_match.group(1).lower()

        if topics_match:
            for line in topics_match.group(1).splitlines():
                line = line.strip().lstrip('-•*').strip()
                if line and line.lower() != 'нет':
                    topics.append(line)

        return sentiment, topics
