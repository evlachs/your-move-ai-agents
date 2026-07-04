"""
tools.py — инструменты агента
AudioScannerTool : сканирует папку на новые аудиофайлы.
SpeechKitTool   : отправляет аудио в Yandex SpeechKit (async), возвращает транскрипт.
YandexGPTTool   : анализирует транскрипт → резюме + список задач.
"""

import base64
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import requests

from configs.config import Config

logger = logging.getLogger(__name__)

SPEECHKIT_RECOGNIZE_URL = 'https://stt.api.cloud.yandex.net/speech/v1/stt:longRunningRecognize'
OPERATIONS_URL = 'https://operation.api.cloud.yandex.net/operations'

# Таблица соответствия расширения → кодировка для SpeechKit
_ENCODING_MAP = {
    '.mp3': 'MP3',
    '.ogg': 'OGG_OPUS',
    '.wav': 'LINEAR16_PCM',
    '.m4a': 'MP3',   # m4a в большинстве случаев совместим с MP3-декодером
}


@dataclass
class MeetingNotes:
    file_name: str
    file_path: str
    processed_at: datetime
    transcript: str
    summary: str
    tasks: list[str] = field(default_factory=list)


# --- Инструмент 1: сканер папки ---

class AudioScannerTool:
    """
    Инструмент для поиска новых аудиофайлов в папке.
    Агент вызывает его чтобы узнать, что появилось с прошлого запуска.
    """

    def __init__(self, config: Config):
        self.audio_dir = Path(config.audio_dir)
        self.extensions = set(config.audio_extensions)

    def scan(self, skip_paths: set[str]) -> list[Path]:
        """
        Возвращает список новых аудиофайлов — тех, которых нет в skip_paths.
        Файлы сортируются по дате изменения (старые первыми).
        """
        if not self.audio_dir.exists():
            logger.warning(f'Папка {self.audio_dir} не существует — создайте её и положите аудиофайлы.')
            return []

        found = [
            p for p in self.audio_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() in self.extensions
            and str(p.resolve()) not in skip_paths
        ]
        found.sort(key=lambda p: p.stat().st_mtime)

        logger.info(f'Папка {self.audio_dir}: найдено {len(found)} новых файлов.')
        return found


# --- Инструмент 2: SpeechKit ---

class SpeechKitTool:
    """
    Инструмент для расшифровки аудио через Yandex SpeechKit.
    Использует асинхронное распознавание: отправляет файл → ждёт результат → возвращает текст.

    Максимальный таймаут: poll_interval × max_polls секунд.
    Если за это время распознавание не завершилось — поднимает TimeoutError.
    """

    def __init__(self, config: Config):
        self.api_key = config.yandex_api_key
        self.folder_id = config.yandex_folder_id
        self.language = config.speechkit_language
        self.model = config.speechkit_model
        self.poll_interval = config.speechkit_poll_interval
        self.max_polls = config.speechkit_max_polls

    @property
    def _headers(self) -> dict:
        return {
            'Authorization': f'Api-Key {self.api_key}',
            'x-folder-id': self.folder_id,
        }

    def recognize(self, file_path: Path) -> str:
        """
        Расшифровывает аудиофайл. Возвращает полный текст транскрипта.
        При сетевой или HTTP-ошибке возвращает пустую строку.
        Если распознавание не завершилось за отведённое время — поднимает TimeoutError.
        """
        logger.info(f'SpeechKit: отправляем {file_path.name} на распознавание...')

        operation_id = self._submit(file_path)
        if not operation_id:
            return ''

        transcript = self._poll(operation_id, file_path.name)
        logger.info(f'SpeechKit: {file_path.name} — транскрипт получен ({len(transcript)} символов).')
        return transcript

    def _submit(self, file_path: Path) -> str | None:
        """Отправляет аудио в SpeechKit. Возвращает ID операции."""
        audio_bytes = file_path.read_bytes()
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        encoding = _ENCODING_MAP.get(file_path.suffix.lower(), 'MP3')

        body = {
            'config': {
                'specification': {
                    'languageCode': self.language,
                    'model': self.model,
                    'audioEncoding': encoding,
                    'profanityFilter': False,
                    'audioChannelCount': 1,
                },
            },
            'audio': {
                'content': audio_b64,
            },
        }

        try:
            response = requests.post(
                SPEECHKIT_RECOGNIZE_URL,
                headers=self._headers,
                json=body,
                timeout=60,
            )
            response.raise_for_status()
            return response.json().get('id')
        except requests.HTTPError as e:
            logger.error(f'SpeechKit ошибка отправки (HTTP {e.response.status_code}): {e.response.text}')
            return None
        except Exception as e:
            logger.error(f'SpeechKit: ошибка при отправке файла: {e}')
            return None

    def _poll(self, operation_id: str, file_name: str) -> str:
        """Ждёт завершения операции и возвращает текст транскрипта."""
        url = f'{OPERATIONS_URL}/{operation_id}'

        for attempt in range(1, self.max_polls + 1):
            time.sleep(self.poll_interval)
            try:
                response = requests.get(url, headers=self._headers, timeout=30)
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logger.warning(f'SpeechKit: ошибка при опросе статуса (попытка {attempt}): {e}')
                continue

            if data.get('done'):
                if 'error' in data:
                    err = data['error']
                    logger.error(f'SpeechKit [{file_name}]: операция завершилась с ошибкой: {err}')
                    return ''
                return self._extract_text(data.get('response', {}))

            logger.debug(f'SpeechKit [{file_name}]: ещё не готово, попытка {attempt}/{self.max_polls}...')

        raise TimeoutError(
            f'SpeechKit: распознавание {file_name} не завершилось за '
            f'{self.poll_interval * self.max_polls} секунд.'
        )

    @staticmethod
    def _extract_text(response: dict) -> str:
        """Собирает текст из всех чанков ответа SpeechKit."""
        chunks = response.get('chunks', [])
        parts = []
        for chunk in chunks:
            alternatives = chunk.get('alternatives', [])
            if alternatives:
                parts.append(alternatives[0].get('text', ''))
        return ' '.join(parts).strip()


# --- Инструмент 3: YandexGPT ---

class YandexGPTTool:
    """Инструмент для анализа транскрипта через YandexGPT."""

    def __init__(self, config: Config):
        self.api_key = config.yandex_api_key
        self.folder_id = config.yandex_folder_id
        self.model = config.yandex_gpt_model

    def _chat(self, system: str, user: str, max_tokens: int = 500) -> str:
        try:
            response = requests.post(
                'https://llm.api.cloud.yandex.net/foundationModels/v1/completion',
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
            if not response.ok:
                logger.error(f'YandexGPT ответ: {response.text}')
                response.raise_for_status()
            return response.json()['result']['alternatives'][0]['message']['text'].strip()
        except Exception as e:
            logger.error(f'Ошибка YandexGPT: {e}')
            return ''

    def analyze_transcript(self, transcript: str, file_name: str) -> tuple[str, list[str]]:
        """
        Анализирует транскрипт встречи.
        Возвращает (краткое резюме, список задач).
        """
        if not transcript:
            return 'Транскрипт пустой или распознавание не удалось.', []

        system = (
            'Ты ассистент, который анализирует транскрипты рабочих встреч. '
            'Ответь СТРОГО в следующем формате, без лишнего текста:\n'
            'РЕЗЮМЕ: краткое описание встречи в 2-3 предложениях\n'
            'ЗАДАЧИ:\n'
            '- первая задача\n'
            '- вторая задача\n'
            '(и так далее; если задач нет — напиши "- нет")'
        )
        # Обрезаем транскрипт, чтобы не переполнить контекст LLM
        truncated = transcript[:6000]
        user = f'Файл: {file_name}\n\nТранскрипт:\n{truncated}'

        raw = self._chat(system, user, max_tokens=600)
        return self._parse_analysis(raw)

    @staticmethod
    def _parse_analysis(raw: str) -> tuple[str, list[str]]:
        summary = 'Анализ недоступен.'
        tasks: list[str] = []

        summary_match = re.search(r'РЕЗЮМЕ:\s*(.+?)(?=ЗАДАЧИ:|$)', raw, re.DOTALL | re.IGNORECASE)
        tasks_match = re.search(r'ЗАДАЧИ:\s*(.+)', raw, re.DOTALL | re.IGNORECASE)

        if summary_match:
            summary = summary_match.group(1).strip()

        if tasks_match:
            raw_tasks = tasks_match.group(1).strip()
            for line in raw_tasks.splitlines():
                line = line.strip().lstrip('-•*').strip()
                if line and line.lower() != 'нет':
                    tasks.append(line)

        return summary, tasks
