"""
tools.py — инструменты агента
IMAP: получаем новые письма из рабочей почты.
YandexGPT: суммаризируем письма и расставляем важность.
"""

import imaplib
import email
import logging
import re
from dataclasses import dataclass
from datetime import datetime, date
from email.header import decode_header
from email.utils import parsedate_to_datetime

import requests

from configs.config import Config


logger = logging.getLogger(__name__)

MAX_BODY_LENGTH = 3000  # символов — обрезаем длинные письма для контекста LLM


@dataclass
class EmailInfo:
    uid: int
    sender: str
    subject: str
    date: datetime
    body: str
    summary: str = ''
    importance: str = ''   # 'высокая' / 'средняя' / 'низкая'


# --- Инструмент 1: IMAP ---

class MailFetcherTool:
    """
    Инструмент для чтения рабочей почты.
    Агент вызывает его чтобы узнать, какие письма пришли с прошлого дайджеста.
    """

    def __init__(self, config: Config):
        self.config = config
        self._conn = None

    @property
    def connection(self) -> imaplib.IMAP4_SSL:
        """Ленивое подключение — один раз при первом обращении."""
        if self._conn is None:
            self._conn = imaplib.IMAP4_SSL(self.config.imap_host, self.config.imap_port)
            self._conn.login(self.config.imap_user, self.config.imap_password)
            self._conn.select(self.config.imap_mailbox, readonly=True)
        return self._conn

    def get_uidnext(self) -> int:
        """UID, который получит следующее письмо — текущая верхняя граница ящика."""
        status, data = self.connection.status(self.config.imap_mailbox, '(UIDNEXT)')
        if status != 'OK' or not data:
            raise RuntimeError(f'Не удалось получить UIDNEXT: {status}')
        match = re.search(rb'UIDNEXT (\d+)', data[0])
        if not match:
            raise RuntimeError(f'Не удалось разобрать ответ STATUS: {data[0]!r}')
        return int(match.group(1))

    def fetch_new_emails(self, last_uid: int | None) -> list[EmailInfo]:
        """
        Возвращает письма с UID больше last_uid.
        Если last_uid is None (первый запуск) — берёт письма за сегодня,
        чтобы не выгружать всю историю почты.
        """
        if last_uid is not None:
            status, data = self.connection.uid('search', None, f'UID {last_uid + 1}:*')
        else:
            since = date.today().strftime('%d-%b-%Y')
            status, data = self.connection.uid('search', None, f'(SINCE {since})')

        if status != 'OK':
            logger.error(f'Ошибка IMAP SEARCH: {status}')
            return []

        uids = [int(u) for u in data[0].split()] if data and data[0] else []
        # 'UID x:*' при отсутствии новых писем может вернуть последний существующий UID —
        # отфильтровываем вручную, чтобы не зацепить уже обработанное письмо
        if last_uid is not None:
            uids = [u for u in uids if u > last_uid]

        result = []
        for uid in sorted(uids):
            raw = self._fetch_raw(uid)
            if raw is None:
                continue
            info = self.parse_email(uid, raw)
            if info:
                result.append(info)

        logger.info(f'IMAP: получено {len(result)} новых писем')
        return result

    def _fetch_raw(self, uid: int) -> bytes | None:
        status, data = self.connection.uid('fetch', str(uid), '(RFC822)')
        if status != 'OK' or not data or data[0] is None:
            logger.warning(f'Не удалось получить письмо UID {uid}')
            return None
        return data[0][1]

    @staticmethod
    def _decode_header_value(value: str) -> str:
        if not value:
            return ''
        parts = decode_header(value)
        decoded = []
        for text, enc in parts:
            if isinstance(text, bytes):
                decoded.append(text.decode(enc or 'utf-8', errors='replace'))
            else:
                decoded.append(text)
        return ''.join(decoded)

    @staticmethod
    def _extract_body(msg: email.message.Message) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain' and not part.get_filename():
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        return payload.decode(charset, errors='replace')
            return ''
        payload = msg.get_payload(decode=True)
        if not payload:
            return ''
        charset = msg.get_content_charset() or 'utf-8'
        return payload.decode(charset, errors='replace')

    @classmethod
    def parse_email(cls, uid: int, raw: bytes) -> EmailInfo | None:
        """
        Разбор письма из сырых байт RFC822 в EmailInfo.
        Чистая функция, не требует IMAP-соединения — легко тестируется.
        """
        try:
            msg = email.message_from_bytes(raw)
        except Exception as e:
            logger.warning(f'Не удалось разобрать письмо UID {uid}: {e}')
            return None

        sender = cls._decode_header_value(msg.get('From', ''))
        subject = cls._decode_header_value(msg.get('Subject', ''))

        try:
            msg_date = parsedate_to_datetime(msg.get('Date'))
        except Exception:
            msg_date = datetime.now()

        body = cls._extract_body(msg).strip()[:MAX_BODY_LENGTH]

        return EmailInfo(uid=uid, sender=sender, subject=subject, date=msg_date, body=body)


# --- Инструмент 2: YandexGPT ---

class YandexGPTTool:
    """Инструмент для анализа писем через YandexGPT."""

    MODEL_LITE = 'yandexgpt-lite'

    def __init__(self, config: Config):
        self.config = config
        self.folder_id = config.yandex_folder_id

    def _chat(self, system: str, user: str, max_tokens: int = 300) -> str:
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

    def analyze_email(self, sender: str, subject: str, body: str) -> tuple[str, str]:
        """
        Возвращает (резюме, важность). Важность — 'высокая'/'средняя'/'низкая'.
        Модель отвечает в фиксированном текстовом формате, который мы разбираем.
        """
        system = (
            'Ты помощник, который анализирует рабочие письма. '
            'Ответь СТРОГО в две строки, без лишнего текста:\n'
            'ВАЖНОСТЬ: высокая|средняя|низкая\n'
            'РЕЗЮМЕ: одно-два предложения на русском о содержании письма'
        )
        user = (
            f'От: {sender}\n'
            f'Тема: {subject}\n'
            f'Текст: {body or "(пусто)"}'
        )
        raw = self._chat(system, user, max_tokens=200)
        return self._parse_analysis(raw)

    @staticmethod
    def _parse_analysis(raw: str) -> tuple[str, str]:
        importance = 'средняя'
        summary = raw.strip()

        importance_match = re.search(r'ВАЖНОСТЬ:\s*(высокая|средняя|низкая)', raw, re.IGNORECASE)
        summary_match = re.search(r'РЕЗЮМЕ:\s*(.+)', raw, re.IGNORECASE | re.DOTALL)

        if importance_match:
            importance = importance_match.group(1).lower()
        if summary_match:
            summary = summary_match.group(1).strip()

        return summary or 'Анализ недоступен.', importance

    def generate_digest_subject(self, emails: list[EmailInfo], period_label: str) -> str:
        """Тема письма-дайджеста — одна фраза."""
        if not emails:
            return f'{period_label}: новых писем нет'

        high = sum(1 for e in emails if e.importance == 'высокая')
        system = 'Ты пишешь тему для email. Одна фраза, максимум 60 символов, на русском.'
        user = (
            f'{period_label}. Всего писем: {len(emails)}, из них важных: {high}. '
            'Напиши тему письма-дайджеста.'
        )
        return self._chat(system, user, max_tokens=60) or f'{period_label}: {len(emails)} новых писем'
