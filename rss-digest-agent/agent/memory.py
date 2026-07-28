"""
memory.py — память агента между запусками
Хранит ID уже виденных записей из RSS-лент —
чтобы одна статья не попадала в дайджест дважды.
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
    Агент спрашивает: «какие записи я уже включал в дайджест?»
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
                CREATE TABLE IF NOT EXISTS seen_entries (
                    entry_id  TEXT PRIMARY KEY,
                    seen_at   TEXT NOT NULL
                );
            """)
        logger.info(f'База данных инициализирована: {self.db_path}')

    def get_seen_ids(self) -> set[str]:
        """Возвращает множество ID уже виденных записей."""
        with self._conn() as conn:
            rows = conn.execute('SELECT entry_id FROM seen_entries').fetchall()
        return {row['entry_id'] for row in rows}

    def mark_seen(self, entry_ids: list[str]):
        """Помечает записи как виденные — после успешной отправки дайджеста."""
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.executemany(
                'INSERT OR IGNORE INTO seen_entries (entry_id, seen_at) VALUES (?, ?)',
                [(eid, now) for eid in entry_ids],
            )
        logger.info(f'Помечено как виденных: {len(entry_ids)} записей.')
