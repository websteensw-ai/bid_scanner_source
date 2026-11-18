"""화면 아이콘 (흑백 실루엣). 출처: game-icons.net (CC BY 3.0) — 저작자 표시는 base.html 바닥글과 NOTICE.md.

이모지 대신 쓴다 (가이드 피드백: 아이콘이 가볍지 않고 신뢰감을 주도록).
"""
import json
from functools import lru_cache
from pathlib import Path

from markupsafe import Markup


@lru_cache
def _icons() -> dict:
    return json.loads((Path(__file__).with_name("icons.json")).read_text(encoding="utf-8"))


def icon(name: str, cls: str = "ic", label: str = "") -> Markup:
    d = _icons()
    body = d["icons"].get(name, "")
    aria = f'role="img" aria-label="{label}"' if label else 'aria-hidden="true"'
    return Markup(f'<svg class="{cls}" viewBox="0 0 {d["width"]} {d["width"]}" fill="currentColor" {aria}>{body}</svg>')
