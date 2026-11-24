"""수집 → ① 읽기 → ② 작성 ⇄ ③ 검수 → 승인 대기 / 자동 게시."""
from __future__ import annotations

import time
from dataclasses import asdict

from . import agents
from .config import read_text
from .llm import LLM, LLMError, LLMRefusal
from .models import Comment
from .platforms.base import Platform
from .store import Store


class Pipeline:
    def __init__(self, cfg: dict, platform: Platform, store: Store, llm: LLM | None):
        self.cfg, self.platform, self.store, self.llm = cfg, platform, store, llm
        self.p = cfg["pipeline"]
        self.c = cfg["claude"]
        self.brand = cfg["brand"]["name"]
        self.guide = read_text(cfg, cfg["brand"]["guide_file"])
        self.faq = read_text(cfg, cfg["brand"]["faq_file"])

    # ───────── 1) 새 댓글 처리 ─────────
    def run(self) -> None:
        comments = self.platform.fetch_comments(self.p["fetch_limit"])
        new = [c for c in comments if not self.store.exists(self.platform.name, c.id)]
        todo = new[: self.p["max_per_run"]]
        print(f"[수집] 가져온 댓글 {len(comments)}개 / 새 댓글 {len(new)}개 / 이번에 처리 {len(todo)}개")

        for i, c in enumerate(todo, 1):
            print(f"\n[{i}/{len(todo)}] {c.author}: {c.text[:60]}")
            try:
                self._process(c)
            except LLMRefusal as e:
                self.store.save(c, "escalated", note=str(e))
                print(f"  → 사람 확인 필요 ({e})")
            except LLMError as e:
                # 저장하지 않으므로 다음 실행 때 다시 시도된다.
                print(f"  → 오류, 다음 실행 때 재시도: {e}")

        if self.p["auto_post"]:
            self.post_approved()

    def _process(self, c: Comment) -> None:
        ctx = self.platform.get_post_context(c.post_id)

        # ① 읽기
        rr = agents.read(self.llm, self.brand, c, ctx, self.c["reader_effort"])
        print(f"  ① 읽기: {rr.category}/{rr.sentiment} 답글={rr.should_reply} 사람={rr.needs_human} - {rr.summary}")
        if rr.needs_human or rr.category == "risky":
            self.store.save(c, "escalated", reader=asdict(rr), note=rr.reason)
            print("  → 사람 확인 필요로 분류")
            return
        if not rr.should_reply or rr.category == "spam":
            self.store.save(c, "skipped", reader=asdict(rr), note=rr.reason)
            print("  → 답글 안 함")
            return

        # ② 작성 ⇄ ③ 검수
        feedback, draft, rv = None, "", None
        for attempt in range(self.p["max_rewrites"] + 1):
            draft = agents.write(self.llm, self.brand, self.guide, self.faq, c, ctx, rr,
                                 feedback, self.c["writer_effort"])
            rv = agents.review(self.llm, self.brand, self.guide, self.faq, c, ctx, draft,
                               self.c["reviewer_effort"])
            print(f"  ② 작성(시도 {attempt + 1}): {draft}")
            print(f"  ③ 검수: {'통과' if rv.approved else '반려 - ' + '; '.join(rv.issues)}")
            if rv.approved:
                break
            feedback = rv.issues + ([rv.suggestion] if rv.suggestion else [])

        if not rv.approved:
            self.store.save(c, "escalated", reader=asdict(rr), draft=draft, review=asdict(rv),
                            note="검수를 통과하지 못함")
            print("  → 검수 반복 실패, 사람 확인 필요")
            return

        auto = self.p["auto_post"] and rr.category in self.p["auto_post_categories"]
        status = "approved" if auto else "pending_approval"
        self.store.save(c, status, reader=asdict(rr), draft=draft, review=asdict(rv))
        print("  → 자동 게시 대기" if auto else "  → 승인 대기 (python main.py review)")

    # ───────── 2) 승인된 답글 게시 ─────────
    def post_approved(self) -> None:
        rows = self.store.by_status(self.platform.name, "approved")
        if not rows:
            print("\n[게시] 게시할 답글이 없습니다.")
            return
        print(f"\n[게시] {len(rows)}개 게시 시작 (간격 {self.p['post_interval_seconds']}초)")
        import json
        for i, row in enumerate(rows):
            c = Comment.from_dict(json.loads(row["comment"]))
            text = row["draft"] + self.p.get("ai_disclosure", "")
            try:
                reply_id = self.platform.post_reply(c, text)
                self.store.update(c.platform, c.id, status="posted", reply_id=reply_id)
                print(f"  ✓ {c.author} 에게 게시: {text}")
            except Exception as e:  # 플랫폼별 예외가 달라 넓게 잡고 기록
                self.store.update(c.platform, c.id, status="failed", note=str(e)[:500])
                print(f"  ✗ 게시 실패 ({c.author}): {e}")
            if i < len(rows) - 1:
                time.sleep(self.p["post_interval_seconds"])
