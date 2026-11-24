"""Facebook 페이지 어댑터 (Graph API, 내 페이지 게시물의 댓글에 대댓글 달기).

인증 파일 secrets/facebook.json
  {"page_id": "페이지 ID", "page_access_token": "페이지 액세스 토큰"}
장기 사용자 토큰으로 받은 페이지 토큰은 만료되지 않는다.
"""
from __future__ import annotations

from ..config import resolve
from ..models import Comment, ThreadMessage
from . import _http
from .base import Platform

EXAMPLE = {"page_id": "1234567890", "page_access_token": "EAAG...(페이지 토큰)"}
HOW = "발급 방법은 README 의 'Facebook 페이지' 항목을 참고하세요."


class FacebookPlatform(Platform):
    name = "facebook"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        fcfg = cfg.get("facebook", {})
        self.base = f"https://graph.facebook.com/{fcfg.get('api_version', 'v23.0')}"
        self.post_limit = int(fcfg.get("post_limit", 10))
        path = resolve(cfg, fcfg.get("token_file", "secrets/facebook.json"))
        self.secret = _http.load_secret(path, ["page_id", "page_access_token"], EXAMPLE, HOW)
        self.page_id = self.secret["page_id"]
        self.token = self.secret["page_access_token"]
        self._texts: dict[str, str] = {}

    def fetch_comments(self, limit: int) -> list[Comment]:
        posts = _http.graph_paged(
            f"{self.base}/{self.page_id}/posts",
            {"fields": "id,message,created_time", "limit": min(self.post_limit, 50),
             "access_token": self.token},
            self.post_limit,
        )
        out: list[Comment] = []
        for p in posts:
            self._texts[p["id"]] = p.get("message", "")
            comments = _http.graph_paged(
                f"{self.base}/{p['id']}/comments",
                {"fields": "id,message,created_time,from{id,name},comments.limit(50){id,message,from{id,name}}",
                 "filter": "toplevel", "order": "reverse_chronological", "limit": 50,
                 "access_token": self.token},
                200,
            )
            for c in comments:
                frm = c.get("from") or {}
                if frm.get("id") == self.page_id:
                    continue  # 페이지가 쓴 댓글
                subs = c.get("comments", {}).get("data", [])
                thread = [ThreadMessage(author=(s.get("from") or {}).get("name", ""),
                                        text=s.get("message", ""),
                                        is_mine=(s.get("from") or {}).get("id") == self.page_id)
                          for s in subs]
                if any(t.is_mine for t in thread):
                    continue
                out.append(Comment(
                    id=c["id"], platform=self.name, post_id=p["id"],
                    author=frm.get("name", "(이름 비공개)"), text=c.get("message", ""),
                    published_at=c.get("created_time", ""), post_title=p.get("message", "")[:50],
                    thread=thread,
                ))
                if len(out) >= limit:
                    return out
        return out

    def get_post_context(self, post_id: str) -> str:
        if post_id not in self._texts:
            r = _http.request("GET", f"{self.base}/{post_id}",
                              params={"fields": "message", "access_token": self.token})
            self._texts[post_id] = r.get("message", "")
        return f"페이지 게시물: {self._texts[post_id][:1500]}"

    def post_reply(self, comment: Comment, text: str) -> str:
        resp = _http.request("POST", f"{self.base}/{comment.id}/comments",
                             form={"message": text, "access_token": self.token})
        return resp["id"]
