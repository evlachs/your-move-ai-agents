"""
notifier.py — отправка дайджеста заметок по встречам
HTML-шаблон живёт в templates/digest.html (Jinja2)
"""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from configs.config import Config
from agent.tools import MeetingNotes

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / 'templates'


class EmailNotifier:
    """
    Отправляет дайджест заметок по встречам на email.
    Агент вызывает send_digest() как последний шаг цикла.
    """

    def __init__(self, config: Config):
        self.config = config
        self.jinja = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=select_autoescape(['html']),
        )

    def send_digest(self, notes_list: list[MeetingNotes]) -> bool:
        """
        Рендерит шаблон и отправляет письмо.
        Возвращает True если письмо ушло успешно.
        """
        if not notes_list:
            logger.info('Нет заметок для отправки.')
            return False

        date_str = datetime.now().strftime('%d.%m.%Y')
        subject = f'[Speech Notes] Заметки по встречам — {date_str} ({len(notes_list)} записей)'
        html = self._render(notes_list, date_str)

        try:
            self._send(subject, html)
            logger.info(f'Дайджест отправлен: {len(notes_list)} записей → {self.config.email_to}')
            return True
        except Exception as e:
            logger.error(f'Ошибка отправки письма: {e}', exc_info=True)
            return False

    def _render(self, notes_list: list[MeetingNotes], date_str: str) -> str:
        template = self.jinja.get_template('digest.html')
        return template.render(
            date_str=date_str,
            notes_list=notes_list,
            total=len(notes_list),
        )

    def _send(self, subject: str, html: str):
        """Отправка через SMTP SSL (порт 465, Яндекс.Почта)."""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.config.email_from
        msg['To'] = self.config.email_to
        msg.attach(MIMEText(html, 'html', 'utf-8'))

        with smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port) as server:
            server.login(self.config.smtp_user, self.config.smtp_password)
            server.sendmail(
                self.config.email_from,
                self.config.email_to,
                msg.as_bytes(),
            )
