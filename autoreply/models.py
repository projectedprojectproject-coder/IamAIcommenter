"""플랫폼에 상관없이 쓰는 공통 데이터 구조."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ThreadMessage:
    """이미 달려 있는 대댓글 한 개 (맥락용)."""
    author: str
    text: str
    is_mine: bool = False


@dataclass
class Comment:
    """답글을 달 대상 댓글."""
    id: str                      # 플랫폼의 댓글 ID (답글 달 때 parent 로 쓰임)
    platform: str                # "youtube", "mock", ...
    post_id: str                 # 영상/게시물 ID
    author: str
    text: str
    published_at: str = ""
    post_title: str = ""
    thread: list[ThreadMessage] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Comment":
        d = dict(d)
        d["thread"] = [ThreadMessage(**t) for t in d.get("thread", [])]
        return cls(**d)


@dataclass
class ReadResult:
    """① 읽기 에이전트 결과."""
    should_reply: bool
    category: str        # question | praise | complaint | feedback | chit_chat | spam | risky
    sentiment: str       # positive | neutral | negative
    summary: str
    needs_human: bool
    reason: str


@dataclass
class ReviewResult:
    """③ 검수 에이전트 결과."""
    approved: bool
    issues: list[str]
    suggestion: str
