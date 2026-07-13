"""
memory.py — память агента между запусками
Хранит ID уже проанализированных отзывов —
чтобы один отзыв не попадал в отчёт дважды.
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
    Агент спрашивает: «какие отзывы я уже анализировал?»
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
                CREATE TABLE IF NOT EXISTS analyzed_reviews (
                    review_id    TEXT PRIMARY KEY,
                    analyzed_at  TEXT NOT NULL
                );
            """)
        logger.info(f'База данных инициализирована: {self.db_path}')

    def get_analyzed_ids(self) -> set[str]:
        """Возвращает множество ID уже проанализированных отзывов."""
        with self._conn() as conn:
            rows = conn.execute('SELECT review_id FROM analyzed_reviews').fetchall()
        return {row['review_id'] for row in rows}

    def mark_analyzed(self, review_ids: list[str]):
        """Помечает отзывы как проанализированные — после успешной отправки отчёта."""
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.executemany(
                'INSERT OR IGNORE INTO analyzed_reviews (review_id, analyzed_at) VALUES (?, ?)',
                [(rid, now) for rid in review_ids],
            )
        logger.info(f'Помечено как проанализированных: {len(review_ids)} отзывов.')
