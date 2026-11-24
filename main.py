"""SNS 대댓글 자동화 실행 진입점.

  python main.py run       새 댓글 수집 → 읽기/작성/검수 → 승인 대기열에 쌓기
  python main.py review    승인 대기 답글을 하나씩 보고 승인/수정/거절
  python main.py post      승인된 답글 게시
  python main.py status    상태별 개수
  python main.py escalated 사람 확인이 필요한 댓글 목록

옵션: --config 다른설정.toml
"""
from __future__ import annotations

import argparse
import json
import sys

from autoreply.config import load_config, resolve
from autoreply.store import Store

STATUS_KO = {
    "skipped": "답글 안 함", "escalated": "사람 확인 필요", "pending_approval": "승인 대기",
    "approved": "게시 대기", "posted": "게시 완료", "rejected": "거절", "failed": "게시 실패",
}


def cmd_review(store: Store, platform_name: str) -> None:
    rows = store.by_status(platform_name, "pending_approval")
    if not rows:
        print("승인 대기 중인 답글이 없습니다.")
        return
    print(f"승인 대기 {len(rows)}개.  [a] 승인  [e] 수정 후 승인  [r] 거절  [s] 건너뛰기  [q] 종료\n")
    for i, row in enumerate(rows, 1):
        c = json.loads(row["comment"])
        reader = json.loads(row["reader"]) if row["reader"] else {}
        print("─" * 60)
        print(f"[{i}/{len(rows)}] {c.get('post_title') or c['post_id']}")
        print(f"댓글  {c['author']}: {c['text']}")
        print(f"분류  {reader.get('category')} / {reader.get('sentiment')}")
        print(f"답글  {row['draft']}")
        choice = input("> ").strip().lower()
        if choice == "a":
            store.update(platform_name, row["comment_id"], status="approved")
        elif choice == "e":
            new = input("수정한 답글: ").strip()
            if new:
                store.update(platform_name, row["comment_id"], status="approved", draft=new)
        elif choice == "r":
            store.update(platform_name, row["comment_id"], status="rejected")
        elif choice == "q":
            break
    print("\n승인한 답글은 'python main.py post' 로 게시하세요.")


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")  # Windows 콘솔 한글 깨짐 방지

    ap = argparse.ArgumentParser(description="SNS 대댓글 자동화 (읽기 → 작성 → 검수)")
    ap.add_argument("command", choices=["run", "review", "post", "status", "escalated"])
    ap.add_argument("--config", default="config.toml")
    args = ap.parse_args()

    cfg = load_config(args.config)
    store = Store(resolve(cfg, cfg["pipeline"]["db_file"]))
    pname = cfg["platform"]

    if args.command == "status":
        counts = store.counts(pname)
        print(f"[{pname}]")
        for k, label in STATUS_KO.items():
            print(f"  {label:10s} {counts.get(k, 0)}")
        return
    if args.command == "review":
        cmd_review(store, pname)
        return
    if args.command == "escalated":
        for row in store.by_status(pname, "escalated"):
            c = json.loads(row["comment"])
            print(f"- {c['author']}: {c['text']}\n    사유: {row['note']}")
        return

    # run / post 는 플랫폼 연결이 필요
    from autoreply.pipeline import Pipeline
    from autoreply.platforms import get_platform

    platform = get_platform(cfg)
    if args.command == "post":
        Pipeline(cfg, platform, store, llm=None).post_approved()
        return

    from autoreply.llm import LLM
    llm = LLM(model=cfg["claude"]["model"], use_fallbacks=cfg["claude"]["use_fallbacks"])
    Pipeline(cfg, platform, store, llm).run()


if __name__ == "__main__":
    main()
