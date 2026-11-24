"""플랫폼 어댑터 등록소. config.toml 의 platform 값으로 선택한다."""
from __future__ import annotations

from .base import Platform


def get_platform(cfg: dict) -> Platform:
    name = cfg["platform"]
    # 각 어댑터는 필요한 라이브러리가 다르므로 선택된 것만 import 한다.
    if name == "youtube":
        from .youtube import YouTubePlatform as cls
    elif name == "mock":
        from .mock import MockPlatform as cls
    elif name == "instagram":
        from .instagram import InstagramPlatform as cls
    elif name == "threads":
        from .threads import ThreadsPlatform as cls
    elif name == "facebook":
        from .facebook import FacebookPlatform as cls
    elif name == "x":
        from .x import XPlatform as cls
    else:
        raise SystemExit(
            f"알 수 없는 platform: {name} (youtube | instagram | threads | facebook | x | mock)")
    return cls(cfg)
