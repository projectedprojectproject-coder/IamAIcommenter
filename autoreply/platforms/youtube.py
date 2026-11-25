"""YouTube Data API v3 어댑터 (내 채널 영상의 댓글에 대댓글 달기).

준비물
1. Google Cloud Console 에서 프로젝트 생성 → "YouTube Data API v3" 사용 설정
2. OAuth 동의 화면 설정 → OAuth 클라이언트 ID(데스크톱 앱) 생성
3. 받은 JSON 을 secrets/client_secret.json 으로 저장
4. 처음 실행하면 브라우저가 열려 채널 계정으로 로그인 → secrets/youtube_token.json 저장

쿼터(기본 하루 10,000 단위): 댓글 목록 조회 1단위, 답글 작성 50단위
→ 하루 약 150~200개 답글이 현실적인 상한.
"""
from __future__ import annotations

import os

from ..config import resolve
from ..models import Comment, ThreadMessage
from .base import Platform

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]


class YouTubePlatform(Platform):
    name = "youtube"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        ycfg = cfg.get("youtube", {})
        self.client_secret = resolve(cfg, ycfg.get("client_secret_file", "secrets/client_secret.json"))
        self.token_file = resolve(cfg, ycfg.get("token_file", "secrets/youtube_token.json"))
        self.video_ids: list[str] = ycfg.get("video_ids", [])
        self.yt = self._build_service()
        self.my_channel_id = self._my_channel_id()
        self._ctx_cache: dict[str, str] = {}

    # ---------- 인증 ----------
    def _build_service(self):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as e:
            raise SystemExit(
                "YouTube 라이브러리가 없습니다. 다음을 실행하세요:\n"
                "  python -m pip install -r requirements.txt"
            ) from e

        creds = None
        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                from google.auth.exceptions import RefreshError
                try:
                    creds.refresh(Request())
                except RefreshError as e:
                    raise SystemExit(
                        "YouTube 로그인 토큰이 만료되었습니다 (테스트 앱은 약 7일마다 만료).\n"
                        f"{self.token_file} 를 지우고 직접 한 번 실행해 다시 로그인하세요."
                    ) from e
            else:
                if not self.client_secret.exists():
                    raise SystemExit(f"OAuth 클라이언트 파일이 없습니다: {self.client_secret}")
                if os.environ.get("AUTOREPLY_UNATTENDED"):
                    # 예약 실행 중에는 브라우저 로그인을 기다리며 멈추지 않도록 바로 종료
                    raise SystemExit("YouTube 로그인이 필요합니다. 직접 한 번 실행해 로그인하세요.")
                flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secret), SCOPES)
                creds = flow.run_local_server(port=0)
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(creds.to_json(), encoding="utf-8")
        return build("youtube", "v3", credentials=creds)

    def _my_channel_id(self) -> str:
        items = self.yt.channels().list(part="id", mine=True).execute().get("items", [])
        if not items:
            raise SystemExit("로그인한 계정에 YouTube 채널이 없습니다.")
        return items[0]["id"]

    # ---------- 댓글 수집 ----------
    def _list_threads(self, limit: int) -> list[dict]:
        threads: list[dict] = []
        targets = [{"videoId": v} for v in self.video_ids] or [
            {"allThreadsRelatedToChannelId": self.my_channel_id}
        ]
        for target in targets:
            page_token = None
            while len(threads) < limit:
                resp = self.yt.commentThreads().list(
                    part="snippet,replies", maxResults=min(100, limit - len(threads)),
                    order="time", textFormat="plainText", pageToken=page_token, **target,
                ).execute()
                threads.extend(resp.get("items", []))
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        return threads[:limit]

    def _all_replies(self, thread: dict) -> list[dict]:
        replies = thread.get("replies", {}).get("comments", [])
        total = thread["snippet"].get("totalReplyCount", 0)
        if total > len(replies):  # commentThreads 는 답글 일부만 주므로 나머지 조회
            replies, page_token = [], None
            while True:
                resp = self.yt.comments().list(
                    part="snippet", parentId=thread["id"], maxResults=100,
                    textFormat="plainText", pageToken=page_token,
                ).execute()
                replies.extend(resp.get("items", []))
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        return replies

    def _author_id(self, snippet: dict) -> str:
        return snippet.get("authorChannelId", {}).get("value", "")

    def fetch_comments(self, limit: int) -> list[Comment]:
        out: list[Comment] = []
        for th in self._list_threads(limit):
            top = th["snippet"]["topLevelComment"]
            s = top["snippet"]
            if self._author_id(s) == self.my_channel_id:
                continue  # 내가 쓴 댓글
            replies = self._all_replies(th)
            thread_msgs = [
                ThreadMessage(
                    author=r["snippet"].get("authorDisplayName", ""),
                    text=r["snippet"].get("textDisplay", ""),
                    is_mine=self._author_id(r["snippet"]) == self.my_channel_id,
                )
                for r in replies
            ]
            if any(m.is_mine for m in thread_msgs):
                continue  # 이미 내가 답한 댓글
            out.append(Comment(
                id=top["id"], platform=self.name, post_id=s.get("videoId", ""),
                author=s.get("authorDisplayName", ""), text=s.get("textDisplay", ""),
                published_at=s.get("publishedAt", ""), thread=thread_msgs,
            ))
        return out

    def get_post_context(self, post_id: str) -> str:
        if post_id not in self._ctx_cache:
            items = self.yt.videos().list(part="snippet", id=post_id).execute().get("items", [])
            sn = items[0]["snippet"] if items else {}
            self._ctx_cache[post_id] = (
                f"영상 제목: {sn.get('title', '')}\n"
                f"영상 설명: {sn.get('description', '')[:1500]}"
            )
        return self._ctx_cache[post_id]

    def already_replied(self, comment: Comment) -> bool:
        page_token = None
        while True:
            resp = self.yt.comments().list(
                part="snippet", parentId=comment.id, maxResults=100,
                textFormat="plainText", pageToken=page_token,
            ).execute()
            if any(self._author_id(r["snippet"]) == self.my_channel_id for r in resp.get("items", [])):
                return True
            page_token = resp.get("nextPageToken")
            if not page_token:
                return False

    # ---------- 게시 ----------
    def post_reply(self, comment: Comment, text: str) -> str:
        resp = self.yt.comments().insert(
            part="snippet",
            body={"snippet": {"parentId": comment.id, "textOriginal": text}},
        ).execute()
        return resp["id"]
