"""Threads 어댑터 (Threads API, 내 게시물에 달린 답글에 대댓글 달기).

인증 파일 secrets/threads.json
  {"access_token": "장기 토큰"}
토큰은 7일마다 자동 갱신된다(60일 만료 방지).
"""
from __future__ import annotations

import time

from ..config import resolve
from ..models import Comment, ThreadMessage
from . import _http
from .base import Platform

BASE = "https://graph.threads.net/v1.0"
EXAMPLE = {"access_token": "THAA...(장기 토큰)"}
HOW = "발급 방법은 README 의 'Threads' 항목을 참고하세요."


class ThreadsPlatform(Platform):
    name = "threads"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        tcfg = cfg.get("threads", {})
        self.media_limit = int(tcfg.get("media_limit", 10))
        self.publish_wait = float(tcfg.get("publish_wait_seconds", 3))
        self.secret_path = resolve(cfg, tcfg.get("token_file", "secrets/threads.json"))
        self.secret = _http.load_secret(self.secret_path, ["access_token"], EXAMPLE, HOW)
        if tcfg.get("auto_refresh_token", True):
            self._maybe_refresh()
        me = self._get("me", fields="id,username")
        self.user_id, self.username = me["id"], me["username"]
        self._texts: dict[str, str] = {}

    @property
    def token(self) -> str:
        return self.secret["access_token"]

    def _get(self, path: str, **params) -> dict:
        return _http.request("GET", f"{BASE}/{path}", params={**params, "access_token": self.token})

    def _maybe_refresh(self) -> None:
        if _http.days_since(self.secret.get("refreshed_at")) < 7:
            return
        try:
            resp = _http.request("GET", "https://graph.threads.net/refresh_access_token",
                                 params={"grant_type": "th_refresh_token", "access_token": self.token})
            self.secret["access_token"] = resp["access_token"]
            self.secret["refreshed_at"] = _http.now_iso()
            _http.save_secret(self.secret_path, self.secret)
            print("[threads] 액세스 토큰을 갱신했습니다.")
        except _http.PlatformAPIError as e:
            print(f"[threads] 토큰 갱신 실패(기존 토큰으로 계속): {e}")

    def fetch_comments(self, limit: int) -> list[Comment]:
        posts = _http.graph_paged(
            f"{BASE}/me/threads",
            {"fields": "id,text,timestamp", "limit": min(self.media_limit, 50), "access_token": self.token},
            self.media_limit,
        )
        out: list[Comment] = []
        for p in posts:
            self._texts[p["id"]] = p.get("text", "")
            # conversation: 게시물 아래의 모든 답글(답글의 답글 포함)을 한 번에 가져온다
            convo = _http.graph_paged(
                f"{BASE}/{p['id']}/conversation",
                {"fields": "id,text,username,timestamp,replied_to", "reverse": "false",
                 "limit": 100, "access_token": self.token},
                500,
            )
            parent = {r["id"]: (r.get("replied_to") or {}).get("id") for r in convo}
            replied_by_me = {parent[r["id"]] for r in convo if r.get("username") == self.username}
            children: dict[str, list[dict]] = {}
            for r in convo:
                children.setdefault(parent[r["id"]], []).append(r)

            for r in convo:
                if parent[r["id"]] != p["id"] or r.get("username") == self.username:
                    continue  # 게시물에 직접 달린 남의 답글만 대상
                if r["id"] in replied_by_me:
                    continue
                thread = [ThreadMessage(author=x.get("username", ""), text=x.get("text", ""),
                                        is_mine=x.get("username") == self.username)
                          for x in children.get(r["id"], [])]
                out.append(Comment(
                    id=r["id"], platform=self.name, post_id=p["id"],
                    author=r.get("username", ""), text=r.get("text", ""),
                    published_at=r.get("timestamp", ""), post_title=p.get("text", "")[:50],
                    thread=thread,
                ))
                if len(out) >= limit:
                    return out
        return out

    def get_post_context(self, post_id: str) -> str:
        if post_id not in self._texts:
            self._texts[post_id] = self._get(post_id, fields="text").get("text", "")
        return f"원글: {self._texts[post_id][:1500]}"

    def post_reply(self, comment: Comment, text: str) -> str:
        # Threads 는 '컨테이너 생성 → 게시' 2단계
        container = _http.request("POST", f"{BASE}/me/threads", form={
            "media_type": "TEXT", "text": text, "reply_to_id": comment.id,
            "access_token": self.token,
        })
        time.sleep(self.publish_wait)
        resp = _http.request("POST", f"{BASE}/me/threads_publish", form={
            "creation_id": container["id"], "access_token": self.token,
        })
        return resp["id"]
