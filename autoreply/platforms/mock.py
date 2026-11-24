"""테스트용 가짜 플랫폼. 실제 SNS 없이 파이프라인 전체를 돌려볼 수 있다.

- 입력: samples/comments.json
- 게시: data/mock_posted.jsonl 에 기록만 한다 (실제로 올라가지 않음)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from ..config import resolve
from ..models import Comment
from .base import Platform


class MockPlatform(Platform):
    name = "mock"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        mcfg = cfg.get("mock", {})
        self.input_file = resolve(cfg, mcfg.get("comments_file", "samples/comments.json"))
        self.output_file = resolve(cfg, mcfg.get("posted_file", "data/mock_posted.jsonl"))
        data = json.loads(self.input_file.read_text(encoding="utf-8"))
        self.posts = {p["id"]: p for p in data["posts"]}
        self.comments = data["comments"]

    def fetch_comments(self, limit: int) -> list[Comment]:
        out = []
        for c in self.comments[:limit]:
            out.append(Comment.from_dict({
                "platform": self.name,
                "post_title": self.posts.get(c["post_id"], {}).get("title", ""),
                **c,
            }))
        return out

    def get_post_context(self, post_id: str) -> str:
        p = self.posts.get(post_id, {})
        return f"제목: {p.get('title', '')}\n설명: {p.get('description', '')}"

    def post_reply(self, comment: Comment, text: str) -> str:
        reply_id = "mock-" + uuid.uuid4().hex[:8]
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with self.output_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "reply_id": reply_id, "parent_id": comment.id, "text": text,
                "posted_at": datetime.now().isoformat(timespec="seconds"),
            }, ensure_ascii=False) + "\n")
        return reply_id
