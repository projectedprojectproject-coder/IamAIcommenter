"""X(Twitter) 어댑터 (X API v2, 내 게시물에 달린 답글에 대댓글 달기).

인증 파일 secrets/x.json  — Developer Portal 의 'Keys and tokens' 에서 복사 (OAuth 1.0a, 만료 없음)
  {"api_key": "...", "api_secret": "...", "access_token": "...", "access_token_secret": "..."}

주의
- 답글 검색(search/recent)은 최근 7일치만, 유료 플랜에서만 가능하다.
- 앱 권한을 'Read and write' 로 바꾼 '뒤에' Access Token 을 발급해야 글쓰기가 된다.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse
import uuid

from ..config import resolve
from ..models import Comment, ThreadMessage
from . import _http
from .base import Platform

BASE = "https://api.x.com/2"
EXAMPLE = {"api_key": "...", "api_secret": "...", "access_token": "...", "access_token_secret": "..."}
HOW = "발급 방법은 README 의 'X (Twitter)' 항목을 참고하세요."


def _enc(s) -> str:
    return urllib.parse.quote(str(s), safe="~")


def oauth1_header(method: str, url: str, query: dict, keys: dict,
                  nonce: str | None = None, timestamp: str | None = None) -> str:
    """OAuth 1.0a HMAC-SHA1 서명 헤더 (JSON 본문은 서명에 포함하지 않는다)."""
    oauth = {
        "oauth_consumer_key": keys["api_key"],
        "oauth_nonce": nonce or uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": keys["access_token"],
        "oauth_version": "1.0",
    }
    pairs = sorted((_enc(k), _enc(v)) for k, v in {**query, **oauth}.items())
    param_str = "&".join(f"{k}={v}" for k, v in pairs)
    base_str = "&".join([method.upper(), _enc(url), _enc(param_str)])
    signing_key = f"{_enc(keys['api_secret'])}&{_enc(keys['access_token_secret'])}"
    sig = base64.b64encode(hmac.new(signing_key.encode(), base_str.encode(), hashlib.sha1).digest()).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{_enc(k)}="{_enc(v)}"' for k, v in sorted(oauth.items()))


class XPlatform(Platform):
    name = "x"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        xcfg = cfg.get("x", {})
        self.post_limit = max(5, min(int(xcfg.get("post_limit", 10)), 100))
        path = resolve(cfg, xcfg.get("token_file", "secrets/x.json"))
        self.keys = _http.load_secret(path, list(EXAMPLE), EXAMPLE, HOW)
        me = self._call("GET", "/users/me")["data"]
        self.user_id, self.username = me["id"], me["username"]
        self._texts: dict[str, str] = {}

    def _call(self, method: str, path: str, params: dict | None = None, json_body: dict | None = None) -> dict:
        url = BASE + path
        auth = oauth1_header(method, url, params or {}, self.keys)
        return _http.request(method, url, params=params, json_body=json_body,
                             headers={"Authorization": auth})

    def fetch_comments(self, limit: int) -> list[Comment]:
        tweets = self._call("GET", f"/users/{self.user_id}/tweets", {
            "max_results": self.post_limit, "exclude": "replies,retweets",
            "tweet.fields": "created_at,conversation_id",
        }).get("data", [])
        out: list[Comment] = []
        for t in tweets:
            self._texts[t["id"]] = t.get("text", "")
            resp = self._call("GET", "/tweets/search/recent", {
                "query": f"conversation_id:{t['id']}", "max_results": 100,
                "tweet.fields": "author_id,created_at,referenced_tweets",
                "expansions": "author_id", "user.fields": "username",
            })
            users = {u["id"]: u["username"] for u in resp.get("includes", {}).get("users", [])}
            replies = resp.get("data", [])

            def parent_of(r: dict) -> str | None:
                return next((x["id"] for x in r.get("referenced_tweets", []) if x["type"] == "replied_to"), None)

            replied_by_me = {parent_of(r) for r in replies if r.get("author_id") == self.user_id}
            children: dict[str, list[dict]] = {}
            for r in replies:
                children.setdefault(parent_of(r), []).append(r)

            for r in replies:
                if parent_of(r) != t["id"] or r.get("author_id") == self.user_id:
                    continue
                if r["id"] in replied_by_me:
                    continue
                thread = [ThreadMessage(author=users.get(x.get("author_id"), ""), text=x.get("text", ""),
                                        is_mine=x.get("author_id") == self.user_id)
                          for x in children.get(r["id"], [])]
                out.append(Comment(
                    id=r["id"], platform=self.name, post_id=t["id"],
                    author=users.get(r.get("author_id"), ""), text=r.get("text", ""),
                    published_at=r.get("created_at", ""), post_title=t.get("text", "")[:50],
                    thread=thread,
                ))
                if len(out) >= limit:
                    return out
        return out

    def get_post_context(self, post_id: str) -> str:
        if post_id not in self._texts:
            self._texts[post_id] = self._call("GET", f"/tweets/{post_id}").get("data", {}).get("text", "")
        return f"원글: {self._texts[post_id]}"

    def post_reply(self, comment: Comment, text: str) -> str:
        resp = self._call("POST", "/tweets", json_body={
            "text": text, "reply": {"in_reply_to_tweet_id": comment.id},
        })
        return resp["data"]["id"]
