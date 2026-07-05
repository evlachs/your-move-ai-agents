"""
memory.py — память агента между запусками
Хранит SHA последнего обработанного коммита, чтобы не генерировать
документацию повторно, если в репозитории ничего не изменилось.
"""

import sqlite3
import logging
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class AgentMemory:
    """
    Тонкая обёртка над SQLite.
    Агент спрашивает: «код менялся с прошлого раза?»
    Если нет — ничего не делает. Если да — генерирует документацию.
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
                CREATE TABLE IF NOT EXISTS repo_state (
                    repo            TEXT PRIMARY KEY,
                    last_commit_sha TEXT NOT NULL,
                    updated_at      TEXT NOT NULL
                );
            """)
        logger.info(f'База данных инициализирована: {self.db_path}')

    def get_last_commit_sha(self, repo: str) -> str | None:
        """SHA коммита, на который сгенерирована последняя документация. None — если ещё не запускались."""
        with self._conn() as conn:
            row = conn.execute(
                'SELECT last_commit_sha FROM repo_state WHERE repo = ?',
                (repo,),
            ).fetchone()
        return row['last_commit_sha'] if row else None

    def set_last_commit_sha(self, repo: str, sha: str):
        """Запомнить SHA коммита после успешного создания PR с документацией."""
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO repo_state (repo, last_commit_sha, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(repo) DO UPDATE SET
                       last_commit_sha = excluded.last_commit_sha,
                       updated_at = excluded.updated_at""",
                (repo, sha, datetime.utcnow().isoformat()),
            )
        logger.info(f'Запомнено: {repo} → {sha[:7]}')
