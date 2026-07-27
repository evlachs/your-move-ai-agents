"""
notifier.py — отправка дайджеста вакансий
HTML-шаблон живёт в templates/digest.html (Jinja2)
"""

import smtplib
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from configs.config import Config
from agent.tools import Vacancy

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / 'templates'


class EmailNotifier:
    """
    Отправляет дайджест новых вакансий на email.
    Агент вызывает send_digest() как последний шаг цикла.
    """

    def __init__(self, config: Config):
        self.config = config
        self.jinja = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=select_autoescape(['html']),
        )

    def send_digest(self, vacancies: list[Vacancy], search_query: str) -> bool:
        """
        Рендерит шаблон и отправляет письмо.
        Возвращает True если письмо ушло успешно.
        """
        date_str = datetime.now().strftime('%d.%m.%Y %H:%M')
        subject = f'[Вакансии] {search_query} — {len(vacancies)} новых ({date_str})'
        html = self._render(vacancies, search_query, date_str)

        try:
            self._send(subject, html)
            logger.info(f'Дайджест отправлен: {len(vacancies)} вакансий → {self.config.email_to}')
            return True
        except Exception as e:
            logger.error(f'Ошибка отправки письма: {e}', exc_info=True)
            return False

    def _render(self, vacancies: list[Vacancy], search_query: str, date_str: str) -> str:
        # Сортируем: интересные — первыми
        order = {'интересная': 0, 'средняя': 1, 'не подходит': 2, '': 3}
        sorted_vacancies = sorted(vacancies, key=lambda v: order.get(v.assessment, 3))

        template = self.jinja.get_template('digest.html')
        return template.render(
            search_query=search_query,
            date_str=date_str,
            vacancies=sorted_vacancies,
            total=len(vacancies),
            interesting=sum(1 for v in vacancies if v.assessment == 'интересная'),
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
