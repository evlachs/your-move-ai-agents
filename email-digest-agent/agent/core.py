"""
core.py — главная логика агента
Цикл: observe → plan → act (анализ) → act (тема) → act (отправка) → observe
"""

import logging

from configs.config import load_config
from agent.memory import AgentMemory
from agent.tools import MailFetcherTool, YandexGPTTool
from agent.notifier import EmailNotifier

logger = logging.getLogger(__name__)


def run(period_label: str = 'Дайджест'):
    """
    Точка входа агента — вызывается из main.py/scheduler.py дважды в день.

    Цикл:
      1. observe — получаем новые письма по IMAP (с UID больше последнего обработанного)
      2. plan    — если писем нет, всё равно сдвигаем границу UID и выходим
      3. act     — анализируем каждое письмо через YandexGPT (резюме + важность)
      4. act     — генерируем тему письма-дайджеста
      5. act     — отправляем дайджест на email
      6. observe — запоминаем новую границу UID (только после успешной отправки)
    """
    config = load_config()

    memory = AgentMemory(config.db_path)
    mail   = MailFetcherTool(config)
    gpt    = YandexGPTTool(config)
    notifier = EmailNotifier(config)

    mailbox = config.imap_mailbox
    logger.info(f'Агент запущен ({period_label}). Почтовый ящик: {mailbox}')

    # ── Шаг 1: observe ──────────────────────────────────────────────

    last_uid = memory.get_last_uid(mailbox)
    new_emails = mail.fetch_new_emails(last_uid)
    uidnext = mail.get_uidnext()

    # ── Шаг 2: plan ─────────────────────────────────────────────────

    if not new_emails:
        logger.info('Новых писем нет — агент завершает работу.')
        memory.set_last_uid(mailbox, uidnext - 1)
        return

    # ── Шаг 3: act — анализ ─────────────────────────────────────────

    for mail_item in new_emails:
        logger.info(f'Анализируем письмо UID {mail_item.uid}: {mail_item.subject}')
        mail_item.summary, mail_item.importance = gpt.analyze_email(
            mail_item.sender, mail_item.subject, mail_item.body,
        )

    # ── Шаг 4: act — тема дайджеста ───────────────────────────────────

    subject_line = gpt.generate_digest_subject(new_emails, period_label)

    # ── Шаг 5: act — отправка ──────────────────────────────────────────

    sent = notifier.send_digest(new_emails, period_label, subject_line)

    # ── Шаг 6: observe — запись в память ────────────────────────────
    # Важно: запоминаем ТОЛЬКО после успешной отправки.
    # Если письмо не ушло — при следующем запуске попробуем снова с тех же писем.

    if sent:
        max_uid = max(e.uid for e in new_emails)
        memory.set_last_uid(mailbox, max_uid)
        logger.info(f'Готово. Обработано писем: {len(new_emails)}')
    else:
        logger.warning(
            'Дайджест не отправлен — память не обновлена. '
            'При следующем запуске попробуем снова.'
        )
