"""
memory.py — память агента между запусками
Хранит UID последнего письма, попавшего в дайджест, по почтовому ящику —
чтобы не включать одно и то же письмо в дайджест дважды.
"""

import sqlite3
import logging
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class AgentMemory:
    """
    Тонкая обёртка над SQLite.
    Агент спрашивает: «какие письма я уже включил в дайджест?»
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
        """Контекстный менеджер соединения — открывает и закрывает сам."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Создаёт таблицу если её ещё нет. Безопасно вызывать при каждом старте."""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS mailbox_state (
                    mailbox    TEXT PRIMARY KEY,
                    last_uid   INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
        logger.info(f'База данных инициализирована: {self.db_path}')

    def get_last_uid(self, mailbox: str) -> int | None:
        """UID последнего письма, включённого в дайджест. None — если ещё не запускались."""
        with self._conn() as conn:
            row = conn.execute(
                'SELECT last_uid FROM mailbox_state WHERE mailbox = ?',
                (mailbox,),
            ).fetchone()
        return row['last_uid'] if row else None

    def set_last_uid(self, mailbox: str, uid: int):
        """Запомнить UID — после успешной отправки дайджеста (или если новых писем не было)."""
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO mailbox_state (mailbox, last_uid, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(mailbox) DO UPDATE SET
                       last_uid = excluded.last_uid,
                       updated_at = excluded.updated_at""",
                (mailbox, uid, datetime.utcnow().isoformat()),
            )
        logger.info(f'Запомнено: {mailbox} → UID {uid}')
