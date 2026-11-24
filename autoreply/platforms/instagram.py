"""Instagram 어댑터 (Instagram Graph API, 내 게시물의 댓글에 대댓글 달기).

인증 파일 secrets/instagram.json
  {"access_token": "장기 토큰"}                       ← login = "instagram" (권장)
  {"access_token": "...", "user_id": "IG 비즈니스 계정 ID"} ← login = "facebook"

- login="instagram": graph.instagram.com 사용, 토큰을 7일마다 자동 갱신(60일 만료 방지)
- login="facebook" : graph.facebook.com 사용, Facebook 페이지에 연결된 IG 계정 필요
"""
from __future__ import annotations

from ..config import resolve
from ..models import Comment, ThreadMessage
from . import _http
from .base import Platform

EXAMPLE = {"access_token": "IGAA...(장기 토큰)"}
HOW = "발급 방법은 README 의 'Instagram' 항목을 참고하세요."


class InstagramPlatform(Platform):
    name = "instagram"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        icfg = cfg.get("instagram", {})
        self.login = icfg.get("login", "instagram")
        ver = icfg.get("api_version", "v23.0")
        host = "graph.instagram.com" if self.login == "instagram" else "graph.facebook.com"
        self.base = f"https://{host}/{ver}"
        self.media_limit = int(icfg.get("media_limit", 10))
        self.secret_path = resolve(cfg, icfg.get("token_file", "secrets/instagram.json"))
        required = ["access_token"] + ([] if self.login == "instagram" else ["user_id"])
        self.secret = _http.load_secret(self.secret_path, required, EXAMPLE, HOW)

        if self.login == "instagram" and icfg.get("auto_refresh_token", True):
            self._maybe_refresh()

        if self.login == "instagram":
            me = self._get("me", fields="user_id,username")
            self.media_owner = "me"
        else:
            me = self._get(self.secret["user_id"], fields="id,username")
            self.media_owner = self.secret["user_id"]
        self.username = me["username"]
        self._captions: dict[str, str] = {}

    @property
    def token(self) -> str:
        return self.secret["access_token"]

    def _get(self, path: str, **params) -> dict:
        return _http.request("GET", f"{self.base}/{path}", params={**params, "access_token": self.token})

    def _maybe_refresh(self) -> None:
        if _http.days_since(self.secret.get("refreshed_at")) < 7:
            return
        try:
            resp = _http.request("GET", "https://graph.instagram.com/refresh_access_token",
                                 params={"grant_type": "ig_refresh_token", "access_token": self.token})
            self.secret["access_token"] = resp["access_token"]
            self.secret["refreshed_at"] = _http.now_iso()
            _http.save_secret(self.secret_path, self.secret)
            print("[instagram] 액세스 토큰을 갱신했습니다.")
        except _http.PlatformAPIError as e:
            print(f"[instagram] 토큰 갱신 실패(기존 토큰으로 계속): {e}")

    def fetch_comments(self, limit: int) -> list[Comment]:
        media = _http.graph_paged(
            f"{self.base}/{self.media_owner}/media",
            {"fields": "id,caption,timestamp", "limit": min(self.media_limit, 50),
             "access_token": self.token},
            self.media_limit,
        )
        out: list[Comment] = []
        for m in media:
            caption = m.get("caption", "")
            self._captions[m["id"]] = caption
            comments = _http.graph_paged(
                f"{self.base}/{m['id']}/comments",
                {"fields": "id,text,username,timestamp,replies{id,text,username,timestamp}",
                 "limit": 50, "access_token": self.token},
                200,
            )
            for c in comments:
                if c.get("username") == self.username:
                    continue  # 내가 쓴 댓글
                replies = c.get("replies", {}).get("data", [])
                thread = [ThreadMessage(author=r.get("username", ""), text=r.get("text", ""),
                                        is_mine=r.get("username") == self.username) for r in replies]
                if any(t.is_mine for t in thread):
                    continue  # 이미 답함
                out.append(Comment(
                    id=c["id"], platform=self.name, post_id=m["id"],
                    author=c.get("username", ""), text=c.get("text", ""),
                    published_at=c.get("timestamp", ""), post_title=caption[:50], thread=thread,
                ))
                if len(out) >= limit:
                    return out
        return out

    def get_post_context(self, post_id: str) -> str:
        if post_id not in self._captions:
            self._captions[post_id] = self._get(post_id, fields="caption").get("caption", "")
        return f"게시물 캡션: {self._captions[post_id][:1500]}"

    def post_reply(self, comment: Comment, text: str) -> str:
        resp = _http.request("POST", f"{self.base}/{comment.id}/replies",
                             form={"message": text, "access_token": self.token})
        return resp["id"]
