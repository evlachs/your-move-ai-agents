"""
notifier.py — отправка email-дайджеста
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
from agent.tools import EmailInfo

logger = logging.getLogger(__name__)

# Папка с шаблонами — рядом с корнем проекта
TEMPLATES_DIR = Path(__file__).parent.parent / 'templates'


class EmailNotifier:
    """
    Отправляет дайджест писем на email.
    Агент вызывает send_digest() как последний шаг цикла.
    """

    def __init__(self, config: Config):
        self.config = config
        self.jinja = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=select_autoescape(['html']),  # защита от XSS автоматически
        )

    def send_digest(self, emails: list[EmailInfo], period_label: str, subject_line: str) -> bool:
        """
        Рендерит шаблон и отправляет письмо.
        Возвращает True если письмо ушло успешно.
        """
        if not emails:
            logger.info('Нет новых писем — дайджест не отправляем.')
            return False

        subject = f'[Email Digest] {subject_line}'
        html = self._render(emails, period_label)

        try:
            self._send(subject, html)
            logger.info(f'Дайджест отправлен: {len(emails)} писем → {self.config.email_to}')
            return True

        except Exception as e:
            logger.error(f'Ошибка отправки письма: {e}', exc_info=True)
            return False

    def _render(self, emails: list[EmailInfo], period_label: str) -> str:
        """Рендерит templates/digest.html с данными агента."""
        important = [e for e in emails if e.importance == 'высокая']
        other = [e for e in emails if e.importance != 'высокая']

        template = self.jinja.get_template('digest.html')
        return template.render(
            period_label=period_label,
            date_str=datetime.now().strftime('%d %B %Y'),
            important=important,
            other=other,
            total=len(emails),
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
