"""
notifier.py — отправка RSS-дайджеста
HTML-шаблон живёт в templates/digest.html (Jinja2)
"""

import smtplib
import logging
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from configs.config import Config
from agent.tools import FeedEntry

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / 'templates'


class EmailNotifier:
    """
    Отправляет дайджест RSS-записей на email.
    Агент вызывает send_digest() как последний шаг цикла.
    """

    def __init__(self, config: Config):
        self.config = config
        self.jinja = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=select_autoescape(['html']),
        )

    def send_digest(self, entries: list[FeedEntry]) -> bool:
        """
        Рендерит шаблон и отправляет письмо.
        Возвращает True если письмо ушло успешно.
        """
        date_str = datetime.now().strftime('%d.%m.%Y')
        subject = f'[RSS Digest] {date_str} — {len(entries)} новых материалов'
        html = self._render(entries, date_str)

        try:
            self._send(subject, html)
            logger.info(f'Дайджест отправлен: {len(entries)} записей → {self.config.email_to}')
            return True
        except Exception as e:
            logger.error(f'Ошибка отправки письма: {e}', exc_info=True)
            return False

    def _render(self, entries: list[FeedEntry], date_str: str) -> str:
        # Группируем записи по названию ленты, сохраняя порядок первого появления
        groups: dict[str, list[FeedEntry]] = defaultdict(list)
        for entry in entries:
            groups[entry.feed_title].append(entry)

        template = self.jinja.get_template('digest.html')
        return template.render(
            date_str=date_str,
            groups=dict(groups),
            total=len(entries),
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
