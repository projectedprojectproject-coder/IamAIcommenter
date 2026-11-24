"""모든 SNS 어댑터가 구현하는 공통 인터페이스.

새 SNS 를 붙이려면 이 클래스를 상속해 세 메서드만 구현하고
platforms/__init__.py 의 REGISTRY 에 등록하면 된다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Comment


class Platform(ABC):
    name: str = "base"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    @abstractmethod
    def fetch_comments(self, limit: int) -> list[Comment]:
        """내 계정 게시물에 달린, 아직 내가 답하지 않은 댓글을 가져온다."""

    @abstractmethod
    def get_post_context(self, post_id: str) -> str:
        """원글(영상 제목/설명 등) 맥락 텍스트."""

    @abstractmethod
    def post_reply(self, comment: Comment, text: str) -> str:
        """댓글에 대댓글을 달고, 생성된 답글 ID 를 반환한다."""
