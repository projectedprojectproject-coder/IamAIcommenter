"""config.toml 읽기 (Python 3.11+ 내장 tomllib 사용, 추가 설치 불필요)."""
from __future__ import annotations

import tomllib
from pathlib import Path

DEFAULTS = {
    "platform": "mock",
    "claude": {
        "model": "claude-opus-5-5",
        "use_fallbacks": True,
        "reader_effort": "low",
        "writer_effort": "medium",
        "reviewer_effort": "medium",
    },
    "brand": {"name": "내 채널", "guide_file": "brand_guide.md", "faq_file": "faq.md"},
    "pipeline": {
        "fetch_limit": 50,
        "max_per_run": 20,
        "max_rewrites": 2,
        "auto_post": False,
        "auto_post_categories": ["praise"],
        "post_interval_seconds": 30,
        "db_file": "data/autoreply.db",
        "ai_disclosure": "",
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise SystemExit(
            f"설정 파일이 없습니다: {path}\n"
            "config.example.toml 을 config.toml 로 복사한 뒤 수정하세요."
        )
    # utf-8-sig: 메모장/PowerShell 이 붙이는 BOM 이 있어도 읽히도록
    cfg = _merge(DEFAULTS, tomllib.loads(path.read_text(encoding="utf-8-sig")))
    cfg["_base_dir"] = str(path.resolve().parent)
    return cfg


def resolve(cfg: dict, rel: str) -> Path:
    """설정 파일 위치 기준 상대 경로를 절대 경로로."""
    p = Path(rel)
    return p if p.is_absolute() else Path(cfg["_base_dir"]) / p


def read_text(cfg: dict, rel: str) -> str:
    p = resolve(cfg, rel)
    return p.read_text(encoding="utf-8") if p.exists() else ""
