"""
notifier.py — отправка email-дайджеста по логам
HTML-шаблон живёт в templates/digest.html (Jinja2)
"""

import smtplib
import logging
from collections import Counter
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from configs.config import Config
from agent.tools import LogEntry

logger = logging.getLogger(__name__)

# Папка с шаблонами — рядом с корнем проекта
TEMPLATES_DIR = Path(__file__).parent.parent / 'templates'


class EmailNotifier:
    """
    Отправляет дайджест по логам на email.
    Агент вызывает send_digest() как последний шаг цикла.
    """

    def __init__(self, config: Config):
        self.config = config
        self.jinja = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=select_autoescape(['html']),  # защита от XSS автоматически
        )

    def send_digest(
        self,
        log_group_id: str,
        level_counts: Counter,
        error_samples: list[LogEntry],
        analysis: str,
        subject_line: str,
    ) -> bool:
        """
        Рендерит шаблон и отправляет письмо.
        Возвращает True если письмо ушло успешно.
        """
        subject = f'[Log Analysis] {subject_line}'
        html = self._render(log_group_id, level_counts, error_samples, analysis)

        try:
            self._send(subject, html)
            total = sum(level_counts.values())
            logger.info(f'Дайджест отправлен: {total} записей → {self.config.email_to}')
            return True

        except Exception as e:
            logger.error(f'Ошибка отправки письма: {e}', exc_info=True)
            return False

    def _render(
        self,
        log_group_id: str,
        level_counts: Counter,
        error_samples: list[LogEntry],
        analysis: str,
    ) -> str:
        """Рендерит templates/digest.html с данными агента."""
        template = self.jinja.get_template('digest.html')
        return template.render(
            log_group_id=log_group_id,
            date_str=datetime.now().strftime('%d %B %Y, %H:%M'),
            level_counts=level_counts.most_common(),
            total=sum(level_counts.values()),
            error_samples=error_samples,
            analysis=analysis,
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
