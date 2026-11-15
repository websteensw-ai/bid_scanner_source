"""글자 수·원고지 배치·문장 유사도·인용 고정 (가이드 7-2·7-3·8-2·8-4).

- official_count: 공식 글자 수. 학생 입력 본문 그대로, 공백·문장부호 포함, 문단 구분 줄바꿈 제외.
  결합 문자(조합형 자모 등)는 앞 글자에 붙여 한 글자로 센다.
- layout: 원고지 배치. 화면 표시에만 쓰며 저장 본문과 공식 글자 수에는 영향을 주지 않는다.
  public/manuscript.js 의 같은 이름 함수와 규칙이 같다 (tests/test_mvp.py 가 확인).
"""
import re
import unicodedata

COLS = 20
ROWS_PER_SHEET = 20
SHEETS = 2
MAX_CELLS = COLS * ROWS_PER_SHEET * SHEETS      # 800
GUIDE_CELL = 700                                 # 2장 15행 끝 = 제출 상한 안내선
HANG = set(".,?!:;'\")」』…·")                    # 줄 첫머리에 오면 앞 줄 끝 칸에 함께 쓰는 부호
_PAIR = re.compile(r"[0-9a-z]")


def official_count(text: str) -> int:
    body = text.replace("\r", "").replace("\n", "")
    return sum(1 for ch in unicodedata.normalize("NFC", body) if not unicodedata.combining(ch))


def _display_paragraph(p: str) -> str:
    p = re.sub(r"\s+", " ", p).strip()
    return re.sub(r"([.,]) ", r"\1", p)


def _tokens(p: str) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(p):
        if _PAIR.match(p[i]) and i + 1 < len(p) and _PAIR.match(p[i + 1]):
            out.append(p[i:i + 2])
            i += 2
        else:
            out.append(p[i])
            i += 1
    return out


def layout(text: str) -> list[list[str]]:
    """원고지 행 목록. 각 행은 20칸(빈 칸은 '')."""
    rows: list[list[str]] = []
    for raw in text.replace("\r", "").split("\n"):
        p = _display_paragraph(raw)
        if not p:
            continue
        row = [""]                     # 문단 첫 칸 비움
        rows.append(row)
        for tok in _tokens(p):
            if len(row) == COLS:
                if tok in HANG:        # 줄 끝 문장부호는 마지막 칸에 함께
                    row[-1] += tok
                    continue
                row = []
                rows.append(row)
            if tok == " " and not row:
                continue               # 줄 첫머리 공백 없음
            row.append(tok)
    return [r + [""] * (COLS - len(r)) for r in rows]


def cells_used(text: str) -> int:
    rows = layout(text)
    if not rows:
        return 0
    last = max((i for i, c in enumerate(rows[-1]) if c), default=-1) + 1
    return (len(rows) - 1) * COLS + last


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+|\n+", text) if len(s.strip()) >= 6]


def _grams(s: str, n: int = 3) -> set[str]:
    s = re.sub(r"\s+", "", s)
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def containment(a: str, b: str) -> float:
    """a 의 3-gram 중 b 에 들어 있는 비율 (0~1). 짧은 a 가 b 를 베꼈는지 볼 때 쓴다."""
    ga, gb = _grams(a), _grams(b)
    return len(ga & gb) / len(ga) if ga else 0.0


def max_overlap(utterance: str, references: list[str]) -> float:
    best = 0.0
    for ref in references:
        for s in sentences(ref) or [ref]:
            best = max(best, containment(utterance, s), containment(s, utterance) if len(s) < 40 else 0)
    return best


def anchor_quote(body: str, start: int, end: int, quote: str) -> tuple[int, int] | None:
    """채점자가 낸 구절 위치 검증·보정 (8-2). 일치하면 그대로, 아니면 본문에서 찾아 보정, 못 찾으면 None."""
    if 0 <= start < end <= len(body) and body[start:end] == quote:
        return start, end
    if quote and (i := body.find(quote)) >= 0:
        return i, i + len(quote)
    return None
