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

    def already_replied(self, comment: Comment) -> bool:
        """지금 시점에 이 댓글에 내 답글이 이미 있는지 확인한다.

        초안을 만든 뒤 SNS 앱에서 직접 답했을 수 있으므로 게시 직전에 다시 확인한다.
        확인 방법이 없는 어댑터는 False(없음)를 돌려준다.
        """
        return False
