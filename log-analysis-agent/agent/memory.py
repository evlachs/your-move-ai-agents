"""
memory.py — память агента между запусками
Хранит границу времени (until), до которой логи уже разобраны и
включены в дайджест — чтобы окно анализа не пересекалось между запусками.
"""

import os
import sqlite3
import logging
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class AgentMemory:
    """
    Тонкая обёртка над SQLite.
    Агент спрашивает: «до какого момента я уже разобрал логи?»
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
        """Создаёт директорию и таблицу если их ещё нет. Безопасно вызывать при каждом старте."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS log_group_state (
                    log_group_id TEXT PRIMARY KEY,
                    last_checked TEXT NOT NULL,
                    updated_at   TEXT NOT NULL
                );
            """)
        logger.info(f'База данных инициализирована: {self.db_path}')

    def get_last_checked(self, log_group_id: str) -> str | None:
        """ISO-таймстамп границы 'until' предыдущего запуска. None — если ещё не запускались."""
        with self._conn() as conn:
            row = conn.execute(
                'SELECT last_checked FROM log_group_state WHERE log_group_id = ?',
                (log_group_id,),
            ).fetchone()
        return row['last_checked'] if row else None

    def set_last_checked(self, log_group_id: str, until_iso: str):
        """Запомнить границу 'until' — только после успешной отправки дайджеста."""
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO log_group_state (log_group_id, last_checked, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(log_group_id) DO UPDATE SET
                       last_checked = excluded.last_checked,
                       updated_at = excluded.updated_at""",
                (log_group_id, until_iso, datetime.utcnow().isoformat()),
            )
        logger.info(f'Запомнено: {log_group_id} → {until_iso}')
