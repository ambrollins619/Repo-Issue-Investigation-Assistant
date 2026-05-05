"""Application metadata and UI projection. LangGraph owns workflow checkpoints."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS investigations (
                id TEXT PRIMARY KEY, issue TEXT NOT NULL, mode TEXT NOT NULL,
                model TEXT NOT NULL, repo_root TEXT NOT NULL, status TEXT NOT NULL,
                state_json TEXT NOT NULL, error TEXT, pending_review TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, issue, settings):
        identifier, timestamp = str(uuid4()), now()
        state = {"issue": issue, "search_rounds": 0, "snippets": [], "report_version": 0, "status": "queued"}
        with self.connect() as db:
            db.execute("INSERT INTO investigations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (identifier, issue, settings.llm_mode, settings.gemini_model, str(settings.repo_root.resolve()),
                        "queued", json.dumps(state), None, None, timestamp, timestamp))
        return self.get(identifier)

    @staticmethod
    def decode(row):
        if row is None:
            return None
        result = dict(row)
        result["state"] = json.loads(result.pop("state_json"))
        result["pending_review"] = json.loads(result["pending_review"]) if result["pending_review"] else None
        return result

    def get(self, identifier):
        with self.connect() as db:
            return self.decode(db.execute("SELECT * FROM investigations WHERE id = ?", (identifier,)).fetchone())

    def history(self, limit=50, offset=0):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id, issue, mode, status, created_at, updated_at FROM investigations ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset))]

    def unfinished(self):
        with self.connect() as db:
            # A published review is already durably paused. Reopening it here could
            # race with a newly submitted review; resume it only through claim_review.
            return [row[0] for row in db.execute("SELECT id FROM investigations WHERE status NOT IN ('accepted', 'failed', 'awaiting_review')")]

    def publish(self, identifier, state, status, error=None, finished=False):
        with self.connect() as db:
            db.execute("""UPDATE investigations SET state_json=?, status=?, error=?, updated_at=?,
                       pending_review=CASE WHEN ? THEN NULL ELSE pending_review END WHERE id=?""",
                       (json.dumps(state), status, error, now(), finished, identifier))

    def claim_review(self, identifier, review):
        with self.connect() as db:
            cursor = db.execute("""UPDATE investigations SET status='queued', pending_review=?, updated_at=?
                WHERE id=? AND status='awaiting_review' AND json_extract(state_json, '$.report_version')=?""",
                (review.model_dump_json(), now(), identifier, review.report_version))
            return cursor.rowcount == 1
