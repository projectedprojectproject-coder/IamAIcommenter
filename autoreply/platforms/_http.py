"""어댑터 공용 HTTP 도우미 (표준 라이브러리 urllib 만 사용, 추가 설치 불필요)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


class PlatformAPIError(Exception):
    def __init__(self, status: int, body: str, url: str):
        self.status, self.body = status, body
        super().__init__(f"HTTP {status} {url}\n{body[:800]}")


def _redact(url: str) -> str:
    return re.sub(r"(access_token=)[^&]+", r"\1***", url)


def encode_query(params: dict) -> str:
    # 공백을 %20 으로 (OAuth 서명과 일치시키기 위해 quote 사용)
    return urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def request(method: str, url: str, params: dict | None = None, form: dict | None = None,
            json_body: dict | None = None, headers: dict | None = None, timeout: int = 30) -> dict:
    if params:
        url += ("&" if "?" in url else "?") + encode_query(params)
    headers = dict(headers or {})
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif json_body is not None:
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise PlatformAPIError(e.code, e.read().decode("utf-8", "replace"), _redact(url)) from None
    except urllib.error.URLError as e:
        raise PlatformAPIError(0, str(e.reason), _redact(url)) from None
    return json.loads(body) if body else {}


def graph_paged(url: str, params: dict, limit: int) -> list[dict]:
    """Meta Graph API(Instagram/Facebook/Threads) 페이지네이션: paging.next 를 따라간다."""
    items: list[dict] = []
    next_url, p = url, params
    while next_url and len(items) < limit:
        resp = request("GET", next_url, params=p)
        items.extend(resp.get("data", []))
        next_url = resp.get("paging", {}).get("next")
        p = None  # next URL 에는 이미 모든 파라미터가 들어 있다
    return items[:limit]


# ───────── 인증 파일 (secrets/*.json) ─────────
def load_secret(path: Path, required: list[str], example: dict, how: str) -> dict:
    if not path.exists():
        raise SystemExit(
            f"인증 파일이 없습니다: {path}\n"
            f"아래 형식으로 만드세요:\n{json.dumps(example, ensure_ascii=False, indent=2)}\n{how}"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise SystemExit(f"{path} 에 다음 값이 없습니다: {', '.join(missing)}")
    return data


def save_secret(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def days_since(iso: str | None) -> float:
    if not iso:
        return 1e9
    return (datetime.now() - datetime.fromisoformat(iso)).total_seconds() / 86400


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
