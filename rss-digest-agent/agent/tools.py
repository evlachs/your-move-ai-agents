"""
tools.py — инструменты агента
RSSFetcherTool : читает записи из списка RSS/Atom-лент через feedparser.
YandexGPTTool  : суммаризирует каждую запись в 1-2 предложения.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime

import feedparser
import requests

from configs.config import Config

logger = logging.getLogger(__name__)

YANDEX_GPT_URL = 'https://llm.api.cloud.yandex.net/foundationModels/v1/completion'

# feedparser.parse() сам управляет HTTP-сессией; User-Agent задаём явно
_USER_AGENT = 'rss-digest-agent/1.0 (educational project)'


@dataclass
class FeedEntry:
    id: str            # guid или ссылка — используется для дедупликации
    feed_title: str    # название ленты (источник)
    title: str
    link: str
    published: datetime | None
    raw_summary: str   # текст сниппета из RSS (после очистки HTML)
    # Заполняется YandexGPT после получения ленты
    digest: str = ''


# --- Инструмент 1: RSS ---

class RSSFetcherTool:
    """
    Инструмент для чтения RSS/Atom-лент.
    Агент вызывает его чтобы получить свежие записи из всех источников.
    """

    def __init__(self, config: Config):
        self.feeds = config.rss_feeds
        self.max_per_feed = config.max_entries_per_feed

    def fetch_all(self) -> list[FeedEntry]:
        """
        Читает все ленты из конфига и возвращает объединённый список записей.
        Записи из каждой ленты ограничены max_entries_per_feed штуками (самые новые).
        """
        result: list[FeedEntry] = []
        for url in self.feeds:
            entries = self._fetch_feed(url)
            result.extend(entries)
        logger.info(f'RSS: получено {len(result)} записей из {len(self.feeds)} лент.')
        return result

    def _fetch_feed(self, url: str) -> list[FeedEntry]:
        """Загружает одну ленту и возвращает список записей."""
        logger.info(f'RSS: загружаем {url}')
        parsed = feedparser.parse(url, agent=_USER_AGENT)

        if parsed.bozo:
            # bozo=True означает, что feedparser поймал ошибку парсинга.
            # Лента при этом могла частично загрузиться, поэтому продолжаем.
            logger.warning(f'RSS [{url}]: ошибка парсинга — {parsed.bozo_exception}')

        feed_title = parsed.feed.get('title') or url
        entries = parsed.entries[: self.max_per_feed]

        result = []
        for entry in entries:
            fe = self._parse_entry(entry, feed_title)
            if fe is not None:
                result.append(fe)

        logger.info(f'RSS [{feed_title}]: {len(result)} записей.')
        return result

    @staticmethod
    def _parse_entry(entry: feedparser.FeedParserDict, feed_title: str) -> FeedEntry | None:
        """Разбирает одну запись feedparser в объект FeedEntry."""
        # ID: предпочитаем guid, иначе ссылка. Без обоих — пропускаем запись.
        entry_id = entry.get('id') or entry.get('link')
        if not entry_id:
            return None

        link = entry.get('link', '')

        # Дата публикации: feedparser даёт time.struct_time или None
        published = None
        if entry.get('published_parsed'):
            try:
                published = datetime(*entry.published_parsed[:6])
            except (TypeError, ValueError):
                pass

        # Сниппет: предпочитаем summary, иначе content[0].value
        raw = ''
        if entry.get('summary'):
            raw = entry.summary
        elif entry.get('content'):
            raw = entry.content[0].get('value', '')

        return FeedEntry(
            id=entry_id,
            feed_title=feed_title,
            title=entry.get('title', ''),
            link=link,
            published=published,
            raw_summary=_strip_html(raw),
        )


def _strip_html(text: str) -> str:
    """Убирает HTML-теги и схлопывает пробелы."""
    clean = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', clean).strip()


# --- Инструмент 2: YandexGPT ---

class YandexGPTTool:
    """Инструмент для суммаризации записей через YandexGPT."""

    # Сколько символов из сниппета передаём в GPT
    _MAX_SNIPPET_LEN = 1500

    def __init__(self, config: Config):
        self.api_key = config.yandex_api_key
        self.folder_id = config.yandex_folder_id
        self.model = config.yandex_gpt_model
        self.topics = config.digest_topics

    def _chat(self, system: str, user: str, max_tokens: int = 150) -> str:
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
                        'temperature': 0.3,
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

    def summarize(self, entry: FeedEntry) -> str:
        """
        Возвращает краткое резюме записи в 1-2 предложениях на русском.
        Если GPT не ответил — возвращает пустую строку.
        """
        topics_line = f'Тематика дайджеста: {self.topics}.\n' if self.topics else ''
        system = (
            f'{topics_line}'
            'Ты редактор новостного дайджеста. '
            'Напиши краткое резюме статьи в 1-2 предложениях на русском языке. '
            'Только суть — без вводных слов и пересказа заголовка.'
        )
        snippet = entry.raw_summary[: self._MAX_SNIPPET_LEN] or entry.title
        user = f'Заголовок: {entry.title}\n\nТекст: {snippet}'

        return self._chat(system, user, max_tokens=150)
