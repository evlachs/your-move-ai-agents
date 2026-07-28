"""
memory.py — память агента между запусками
Хранит историю опубликованных черновиков: какие темы уже использовались
(чтобы не повторяться) и на какие даты уже запланированы посты
(чтобы не создавать дубликаты при повторном запуске).
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
    Агент спрашивает: «на эту дату уже есть черновик?» и «какие темы я уже брал?»
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
                CREATE TABLE IF NOT EXISTS posts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic       TEXT NOT NULL,
                    text        TEXT NOT NULL,
                    vk_post_id  TEXT NOT NULL,
                    publish_at  TEXT NOT NULL,
                    created_at  TEXT NOT NULL
                );
            """)
        logger.info(f'База данных инициализирована: {self.db_path}')

    def recent_topics(self, limit: int = 20) -> list[str]:
        """Темы последних N постов — передаём модели, чтобы она не повторялась."""
        with self._conn() as conn:
            rows = conn.execute(
                'SELECT topic FROM posts ORDER BY id DESC LIMIT ?',
                (limit,),
            ).fetchall()
        return [row['topic'] for row in rows]

    def has_post_for(self, publish_date: str) -> bool:
        """True если на эту дату (YYYY-MM-DD) уже запланирован черновик."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM posts WHERE date(publish_at) = date(?)",
                (publish_date,),
            ).fetchone()
        return row is not None

    def save_post(self, topic: str, text: str, vk_post_id: str, publish_at: str):
        """Запомнить созданный черновик — только после успешной публикации в VK."""
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO posts (topic, text, vk_post_id, publish_at, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (topic, text, vk_post_id, publish_at, datetime.utcnow().isoformat()),
            )
        logger.info(f'Запомнен черновик: "{topic}" → VK post {vk_post_id}, публикация {publish_at}')
