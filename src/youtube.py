"""유튜브 주소 확인과 자막·채팅 수집 (yt-dlp).

서버에서 유튜브 요청이 차단될 수 있다. 차단되면 예외를 그대로 올려 화면에 안내한다.
"""
from __future__ import annotations

import pathlib
import re
import tempfile

_ID_RE = re.compile(r"(?:v=|youtu\.be/|/live/|/shorts/)([A-Za-z0-9_-]{11})")
_BARE_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTubeError(Exception):
    pass


def parse_video_id(url: str) -> str:
    """유튜브 주소 또는 11자리 영상 ID에서 영상 ID를 꺼낸다."""
    url = (url or "").strip()
    if _BARE_RE.match(url):
        return url
    m = _ID_RE.search(url)
    if not m or "youtube" not in url and "youtu.be" not in url:
        raise YouTubeError("유튜브 주소가 아닙니다. 예: https://www.youtube.com/watch?v=영상ID")
    return m.group(1)


def fetch_captions_and_chat(video_id: str, workdir: str | None = None) -> dict:
    """자동자막(ko)과 채팅 리플레이를 내려받아 파일 경로를 돌려준다."""
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover
        raise YouTubeError("yt-dlp가 설치되어 있지 않습니다.") from exc

    out = pathlib.Path(workdir or tempfile.mkdtemp(prefix="takers_"))
    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["ko.*", "live_chat"],
        "subtitlesformat": "vtt/json",
        "outtmpl": str(out / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:  # 네트워크 차단, 영상 없음 등
        raise YouTubeError(f"유튜브에서 자료를 가져오지 못했습니다: {exc}") from exc

    files = {"vtt": None, "chat": None}
    for p in out.glob(f"{video_id}*"):
        name = p.name
        if name.endswith(".vtt") and files["vtt"] is None:
            files["vtt"] = p
        if "live_chat" in name and files["chat"] is None:
            files["chat"] = p
    return {
        "title": info.get("title", ""),
        "duration_min": round((info.get("duration") or 0) / 60, 1),
        "vtt": files["vtt"],
        "chat": files["chat"],
    }
