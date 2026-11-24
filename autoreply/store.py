"""처리 상태 저장 (SQLite). 같은 댓글에 두 번 답하지 않게 막는 역할.

status 값
- skipped           : 답할 필요 없음 (스팸 등)
- escalated         : 사람이 직접 처리해야 함 (위험/검수 실패/거절)
- pending_approval  : 검수 통과, 사람 승인 대기
- approved          : 승인됨, 게시 대기
- posted            : 게시 완료
- rejected          : 사람이 거절
- failed            : 게시 중 오류
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import Comment

SCHEMA = """
CREATE TABLE IF NOT EXISTS comments (
    platform    TEXT NOT NULL,
    comment_id  TEXT NOT NULL,
    status      TEXT NOT NULL,
    comment     TEXT NOT NULL,
    reader      TEXT,
    draft       TEXT,
    review      TEXT,
    note        TEXT,
    reply_id    TEXT,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (platform, comment_id)
);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def exists(self, platform: str, comment_id: str) -> bool:
        return self.db.execute(
            "SELECT 1 FROM comments WHERE platform=? AND comment_id=?", (platform, comment_id)
        ).fetchone() is not None

    def save(self, c: Comment, status: str, reader=None, draft=None, review=None, note=None):
        self.db.execute(
            """INSERT OR REPLACE INTO comments
               (platform, comment_id, status, comment, reader, draft, review, note, reply_id, updated_at)
               VALUES (?,?,?,?,?,?,?,?,NULL,?)""",
            (c.platform, c.id, status, json.dumps(c.to_dict(), ensure_ascii=False),
             json.dumps(reader, ensure_ascii=False) if reader else None,
             draft, json.dumps(review, ensure_ascii=False) if review else None,
             note, _now()),
        )
        self.db.commit()

    def update(self, platform: str, comment_id: str, **fields):
        fields["updated_at"] = _now()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(
            f"UPDATE comments SET {cols} WHERE platform=? AND comment_id=?",
            (*fields.values(), platform, comment_id),
        )
        self.db.commit()

    def by_status(self, platform: str, status: str) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM comments WHERE platform=? AND status=? ORDER BY updated_at",
            (platform, status),
        ).fetchall()

    def counts(self, platform: str) -> dict[str, int]:
        rows = self.db.execute(
            "SELECT status, COUNT(*) n FROM comments WHERE platform=? GROUP BY status", (platform,)
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
