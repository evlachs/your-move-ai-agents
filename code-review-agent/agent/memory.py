"""
memory.py — память агента между запусками
Хранит ключи вида "{pr_number}:{head_sha}" для уже проревьюенных PR.
Если в PR появляются новые коммиты (меняется head_sha) — агент проведёт ревью заново.
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
    Агент спрашивает: «проводил ли я ревью этой версии PR?»
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
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
                CREATE TABLE IF NOT EXISTS reviewed_prs (
                    review_key   TEXT PRIMARY KEY,
                    reviewed_at  TEXT NOT NULL
                );
            """)
        logger.info(f'База данных инициализирована: {self.db_path}')

    def get_reviewed_keys(self) -> set[str]:
        """Возвращает множество ключей уже проревьюенных версий PR."""
        with self._conn() as conn:
            rows = conn.execute('SELECT review_key FROM reviewed_prs').fetchall()
        return {row['review_key'] for row in rows}

    def mark_reviewed(self, review_key: str):
        """Помечает версию PR как проревьюенную — после успешной публикации ревью."""
        with self._conn() as conn:
            conn.execute(
                'INSERT OR IGNORE INTO reviewed_prs (review_key, reviewed_at) VALUES (?, ?)',
                (review_key, datetime.utcnow().isoformat()),
            )
        logger.info(f'Помечено как проревьюенное: {review_key}')
