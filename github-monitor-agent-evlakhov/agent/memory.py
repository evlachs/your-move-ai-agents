"""
memory.py — память агента между запусками
Хранит уже обработанные PR и коммиты чтобы не слать одно и то же дважды
"""

import sqlite3
import logging
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class AgentMemory:
    """
    Тонкая обёртка над SQLite.
    Агент спрашивает: «я это уже видел?»
    Если нет — обрабатывает и запоминает.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
        """Контекстный менеджер соединения — открывает и закрывает сам."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # результаты как словари
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Создаёт таблицы если их ещё нет. Безопасно вызывать при каждом старте."""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS seen_prs (
                    pr_id     INTEGER NOT NULL,
                    repo      TEXT    NOT NULL,
                    title     TEXT,
                    seen_at   TEXT    NOT NULL,
                    PRIMARY KEY (pr_id, repo)
                );

                CREATE TABLE IF NOT EXISTS seen_commits (
                    sha       TEXT    NOT NULL,
                    repo      TEXT    NOT NULL,
                    message   TEXT,
                    seen_at   TEXT    NOT NULL,
                    PRIMARY KEY (sha, repo)
                );
            """)
        logger.info(f'База данных инициализирована: {self.db_path}')

    # --- PR ---

    def is_new_pr(self, pr_id: int, repo: str) -> bool:
        """True если этот PR ещё не попадал в дайджест."""
        with self._conn() as conn:
            row = conn.execute(
                'SELECT 1 FROM seen_prs WHERE pr_id = ? AND repo = ?',
                (pr_id, repo),
            ).fetchone()
        return row is None

    def mark_pr_seen(self, pr_id: int, repo: str, title: str):
        """Запомнить что этот PR уже отправлен."""
        with self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO seen_prs (pr_id, repo, title, seen_at)
                   VALUES (?, ?, ?, ?)""",
                (pr_id, repo, title, datetime.utcnow().isoformat()),
            )

    def filter_new_prs(self, prs: list, repo: str) -> list:
        """
        Из списка PR вернуть только новые.
        prs — список объектов с атрибутами .number и .title (PyGitHub PullRequest)
        """
        return [pr for pr in prs if self.is_new_pr(pr.number, repo)]

    # --- Коммиты ---

    def is_new_commit(self, sha: str, repo: str) -> bool:
        """True если этот коммит ещё не попадал в дайджест."""
        with self._conn() as conn:
            row = conn.execute(
                'SELECT 1 FROM seen_commits WHERE sha = ? AND repo = ?',
                (sha, repo),
            ).fetchone()
        return row is None

    def mark_commit_seen(self, sha: str, repo: str, message: str):
        """Запомнить что этот коммит уже отправлен."""
        with self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO seen_commits (sha, repo, message, seen_at)
                   VALUES (?, ?, ?, ?)""",
                (sha, repo, message, datetime.utcnow().isoformat()),
            )

    def filter_new_commits(self, commits: list, repo: str) -> list:
        """
        Из списка коммитов вернуть только новые.
        commits — список объектов с атрибутами .sha и .commit.message (PyGitHub Commit)
        """
        return [c for c in commits if self.is_new_commit(c.sha, repo)]

    # --- Утилиты ---

    def mark_prs_seen_bulk(self, prs: list, repo: str):
        """Запомнить сразу список PR после успешной отправки дайджеста."""
        for pr in prs:
            self.mark_pr_seen(pr.number, repo, pr.title)
        logger.info(f'Запомнено {len(prs)} новых PR для {repo}')

    def mark_commits_seen_bulk(self, commits: list, repo: str):
        """Запомнить сразу список коммитов после успешной отправки дайджеста."""
        for c in commits:
            self.mark_commit_seen(c.sha, repo, c.message)
            logger.info(f'Запомнено {len(commits)} новых коммитов для {repo}')

    def stats(self, repo: str) -> dict:
        """Статистика для отладки — сколько всего помним."""
        with self._conn() as conn:
            pr_count = conn.execute(
                'SELECT COUNT(*) FROM seen_prs WHERE repo = ?', (repo,)
            ).fetchone()[0]
            commit_count = conn.execute(
                'SELECT COUNT(*) FROM seen_commits WHERE repo = ?', (repo,)
            ).fetchone()[0]
        return {'repo': repo, 'seen_prs': pr_count, 'seen_commits': commit_count}
