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
from agent.tools import PRInfo, CommitInfo

logger = logging.getLogger(__name__)

# Папка с шаблонами — рядом с корнем проекта
TEMPLATES_DIR = Path(__file__).parent.parent / 'templates'


class EmailNotifier:
    """
    Отправляет дайджест на email.
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
        repo: str,
        new_prs: list[PRInfo],
        new_commits: list[CommitInfo],
        commits_summary: str,
        subject_line: str,
    ) -> bool:
        """
        Рендерит шаблон и отправляет письмо.
        Возвращает True если письмо ушло успешно.
        """
        if not new_prs and not new_commits:
            logger.info('Нет новых событий — письмо не отправляем.')
            return False

        subject = f'[GitHub Monitor] {subject_line}'
        html = self._render(repo, new_prs, new_commits, commits_summary)

        try:
            self._send(subject, html)
            logger.info(
                f'Дайджест отправлен: {len(new_prs)} PR, '
                f'{len(new_commits)} коммитов → {self.config.email_to}'
            )
            return True

        except Exception as e:
            logger.error(f'Ошибка отправки письма: {e}', exc_info=True)
            return False

    def _render(
        self,
        repo: str,
        prs: list[PRInfo],
        commits: list[CommitInfo],
        commits_summary: str,
    ) -> str:
        """Рендерит templates/digest.html с данными агента."""
        template = self.jinja.get_template('digest.html')
        return template.render(
            repo=repo,
            date_str=datetime.now().strftime('%d %B %Y'),
            prs=prs,
            commits=commits,
            commits_summary=commits_summary,
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