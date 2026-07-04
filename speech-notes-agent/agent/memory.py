"""
memory.py — память агента между запусками
Хранит пути к уже обработанным аудиофайлам —
чтобы не расшифровывать одну запись дважды.
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
    Агент спрашивает: «какие файлы я уже расшифровал?»
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
                CREATE TABLE IF NOT EXISTS processed_files (
                    file_path  TEXT PRIMARY KEY,
                    processed_at TEXT NOT NULL
                );
            """)
        logger.info(f'База данных инициализирована: {self.db_path}')

    def get_processed_files(self) -> set[str]:
        """Возвращает множество путей уже обработанных файлов."""
        with self._conn() as conn:
            rows = conn.execute('SELECT file_path FROM processed_files').fetchall()
        return {row['file_path'] for row in rows}

    def add_processed_file(self, file_path: str):
        """Запомнить файл — после успешной отправки заметок."""
        with self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO processed_files (file_path, processed_at)
                   VALUES (?, ?)""",
                (file_path, datetime.utcnow().isoformat()),
            )
        logger.info(f'Запомнено: {file_path}')
