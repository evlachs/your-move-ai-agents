"""
tools.py — инструменты агента
Yandex Cloud Logging: получаем записи логов за период.
YandexGPT: анализируем ошибки и формулируем тему дайджеста.
"""

import logging
from collections import Counter
from dataclasses import dataclass

import requests

from configs.config import Config


logger = logging.getLogger(__name__)

ERROR_LEVELS = {'ERROR', 'FATAL'}
MAX_ERROR_SAMPLES = 20
MAX_MESSAGE_LENGTH = 300  # символов — обрезаем длинные сообщения для контекста LLM


@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    resource_type: str
    resource_id: str


# --- Инструмент 1: Yandex Cloud Logging ---

class LogFetcherTool:
    """
    Инструмент для чтения логов из Yandex Cloud Logging.
    Агент вызывает его, чтобы узнать что произошло за последний период.
    """

    READ_URL = 'https://logging.api.cloud.yandex.net/logging/v1/read'

    def __init__(self, config: Config):
        self.config = config

    def fetch_entries(self, since: str, until: str) -> list[LogEntry]:
        """
        Возвращает все записи лог-группы за период [since, until),
        постранично проходя по nextPageToken.
        """
        entries = []
        page_token = None

        while True:
            body = {
                'logGroupId': self.config.log_group_id,
                'since': since,
                'until': until,
                'pageSize': 100,
            }
            if page_token:
                body['pageToken'] = page_token

            try:
                response = requests.post(
                    self.READ_URL,
                    headers={'Authorization': f'Bearer {self.config.yc_iam_token}'},
                    json=body,
                    timeout=30,
                )
                if not response.ok:
                    logger.error(f'Yandex Cloud Logging ответ: {response.text}')
                    response.raise_for_status()
                data = response.json()

            except Exception as e:
                logger.error(f'Ошибка запроса к Yandex Cloud Logging: {e}')
                break

            for raw in data.get('entries', []):
                entries.append(LogEntry(
                    timestamp=raw.get('timestamp', ''),
                    level=raw.get('level', 'UNSPECIFIED'),
                    message=(raw.get('message') or '')[:MAX_MESSAGE_LENGTH],
                    resource_type=raw.get('resource', {}).get('type', ''),
                    resource_id=raw.get('resource', {}).get('id', ''),
                ))

            page_token = data.get('nextPageToken')
            if not page_token:
                break

        logger.info(f'Yandex Cloud Logging: получено {len(entries)} записей за период')
        return entries


def aggregate_logs(entries: list[LogEntry]) -> tuple[Counter, list[LogEntry]]:
    """
    Чистая функция агрегации — без обращения к сети, легко тестируется.
    Возвращает счётчик записей по уровням и до MAX_ERROR_SAMPLES примеров ERROR/FATAL.
    """
    level_counts = Counter(e.level for e in entries)
    error_samples = [e for e in entries if e.level in ERROR_LEVELS][:MAX_ERROR_SAMPLES]
    return level_counts, error_samples


# --- Инструмент 2: YandexGPT ---

class YandexGPTTool:
    """Инструмент для анализа логов через YandexGPT."""

    MODEL_LITE = 'yandexgpt-lite'

    def __init__(self, config: Config):
        self.config = config
        self.folder_id = config.yandex_folder_id

    def _chat(self, system: str, user: str, max_tokens: int = 600) -> str:
        try:
            response = requests.post(
                'https://llm.api.cloud.yandex.net/foundationModels/v1/completion',
                headers={
                    'Authorization': f'Api-Key {self.config.yandex_api_key}',
                    'x-folder-id': self.folder_id,
                },
                json={
                    'modelUri': f'gpt://{self.folder_id}/{self.MODEL_LITE}',
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
            if not response.ok:
                logger.error(f'YandexGPT ответ: {response.text}')
                response.raise_for_status()
            return response.json()['result']['alternatives'][0]['message']['text'].strip()

        except Exception as e:
            logger.error(f'Ошибка YandexGPT: {e}')
            return ''

    def analyze_logs(self, level_counts: Counter, error_samples: list[LogEntry]) -> str:
        """
        Анализирует распределение по уровням и примеры ошибок.
        Возвращает краткий текст: возможные причины, на что обратить внимание.
        """
        if not error_samples:
            return 'Ошибок и сбоев за период не обнаружено.'

        counts_line = ', '.join(f'{level}: {count}' for level, count in level_counts.most_common())
        samples_block = '\n'.join(f'- [{e.timestamp}] {e.message}' for e in error_samples)

        system = (
            'Ты SRE-инженер, анализирующий логи сервиса в Yandex Cloud. '
            'Кратко (3-5 предложений, на русском) опиши: какие проблемы видны, '
            'есть ли повторяющийся паттерн, на что обратить внимание разработчику.'
        )
        user = (
            f'Распределение записей по уровням: {counts_line}\n\n'
            f'Примеры ошибок:\n{samples_block}'
        )
        return self._chat(system, user) or 'Анализ недоступен.'

    def generate_digest_subject(self, level_counts: Counter) -> str:
        """Тема письма-дайджеста — одна фраза."""
        errors = sum(level_counts.get(level, 0) for level in ERROR_LEVELS)
        if errors == 0:
            return 'Логи в норме, ошибок не обнаружено'

        system = 'Ты пишешь тему для email. Одна фраза, максимум 60 символов, на русском.'
        user = f'За период обнаружено {errors} ошибок в логах. Напиши тему письма-дайджеста.'
        return self._chat(system, user, max_tokens=60) or f'Обнаружено {errors} ошибок в логах'
