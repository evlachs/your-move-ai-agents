"""
notifier.py — отправка HTML-отчёта о тональности отзывов на email
"""

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from configs.config import Config
from agent.tools import Review

logger = logging.getLogger(__name__)

# Папка с шаблонами — рядом с корнем проекта. Абсолютный путь, а не 'templates':
# иначе поиск шаблона зависел бы от текущей рабочей директории процесса
# (которая может не совпадать с корнем агента — cron, systemd, другой WORKDIR).
TEMPLATES_DIR = Path(__file__).parent.parent / 'templates'


class EmailNotifier:
    """Рендерит HTML-шаблон и доставляет отчёт через SMTP SSL."""

    def __init__(self, config: Config):
        self.smtp_host = config.smtp_host
        self.smtp_port = config.smtp_port
        self.smtp_user = config.smtp_user
        self.smtp_password = config.smtp_password
        self.email_from = config.email_from
        self.email_to = config.email_to

        self._jinja = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=select_autoescape(['html']),
        )

    def send(self, reviews: list[Review], summary: str) -> bool:
        """
        Отправляет HTML-отчёт по результатам анализа.
        Возвращает True если письмо отправлено успешно.
        """
        html = self._render(reviews, summary)
        total = len(reviews)
        neg = sum(1 for r in reviews if r.sentiment == 'негативный')
        subject = (
            f'Отчёт по отзывам ({total} новых, {neg} негативных) — '
            f'{datetime.now().strftime("%d.%m.%Y")}'
        )

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.email_from
        msg['To'] = self.email_to
        msg.attach(MIMEText(html, 'html', 'utf-8'))

        try:
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.email_from, [self.email_to], msg.as_string())
            logger.info(f'Отчёт отправлен на {self.email_to} (отзывов: {total}).')
            return True
        except Exception as e:
            logger.error(f'Ошибка при отправке письма: {e}')
            return False

    def _render(self, reviews: list[Review], summary: str) -> str:
        neg = [r for r in reviews if r.sentiment == 'негативный']
        neutral = [r for r in reviews if r.sentiment == 'нейтральный']
        pos = [r for r in reviews if r.sentiment == 'позитивный']

        template = self._jinja.get_template('digest.html')
        return template.render(
            generated_at=datetime.now().strftime('%d.%m.%Y %H:%M'),
            total=len(reviews),
            positive=pos,
            neutral=neutral,
            negative=neg,
            summary=summary,
        )
