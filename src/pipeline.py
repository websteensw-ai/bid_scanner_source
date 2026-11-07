"""테이커스 비전 기호 분석시스템 - 분석 파이프라인.

입력: 유튜브 자동자막(VTT), 채팅 리플레이(live_chat JSONL)
출력: 핵심어 빈도, 공출현 네트워크, 참여 유형, 분 단위 시계열
"""
from __future__ import annotations

import collections
import itertools
import json
import re
from dataclasses import dataclass, field

import networkx as nx
from networkx.algorithms import community as nx_community

DEFAULT_STOP = set(
    "그냥 이거 저거 그거 이제 지금 여기 저기 우리 저희 여러분 분들 하나 그리고 이것 저것 그것 "
    "정도 같은 이런 저런 그런 것 거 수 곳 때 말 좀 진짜 아주 너무 많이 해요 합니다 있습니다 "
    "있어요 되게 자 네 예 아 어 음 응 야 뭐 게 쪽 번 개 분 부터 까지 에서 으로 이제 "
    "안녕하세요 감사합니다 감사".split()
)

# 채팅 참여 유형 사전. 위에서부터 먼저 맞는 규칙이 배정됨.
CHAT_CATEGORIES = [
    ("구매 언급", r"구매|주문|샀|구입|결제|링크|스마트스토어|사러|장바구니|가격|배송"),
    ("판매 응원(완판)", r"완판|완매|품절|매진|대박|판매|잘팔"),
    ("진행 요청", r"얼릉|얼른|빨리|나오세요|시작|말고|드세요|먹으|먹어|진행"),
    ("감각적 반응", r"먹고|먹고 싶|맛있|맛|군침|굽|구워|고소|육즙|마블링"),
    ("상품 선호", r"부채살|등심|안심|채끝|살치|꽃등심|좋아|등급|우대"),
    ("팬덤 응원", r"응원|화이팅|왕자|사랑|가수|파이팅|팬|하트|red_heart|최고"),
    ("지역·축제 관심", r"장수|축제|사과|레드|여행|관광|지역|고향|생산"),
]
CHAT_OTHER = "기타"

TAG_RE = re.compile(r"\[(음악|박수|웃음)\]")
VTT_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class ChatMessage:
    t: float
    author: str
    text: str
    category: str = CHAT_OTHER
    author_id: str = ""


@dataclass
class AnalysisResult:
    segments: list = field(default_factory=list)
    chat: list = field(default_factory=list)
    term_freq: list = field(default_factory=list)
    graph_nodes: list = field(default_factory=list)
    graph_edges: list = field(default_factory=list)
    communities: list = field(default_factory=list)
    category_counts: list = field(default_factory=list)
    per_minute: dict = field(default_factory=dict)
    sale_talk_per_minute: dict = field(default_factory=dict)
    correlation: float | None = None


def _ts(s: str) -> float:
    h, m, rest = s.split(":")
    sec, ms = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000


def parse_vtt(text: str) -> list[Segment]:
    """YouTube 자동자막(VTT)을 구간 목록으로 바꾼다.

    자동자막은 같은 문장이 여러 구간에 걸쳐 반복되므로, 인라인 타임코드(<..>)가 없는
    '확정된' 줄만 취하고 연속 중복은 합친다.
    """
    segs: list[Segment] = []
    for block in text.split("\n\n"):
        lines = [l for l in block.split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if "-->" not in line:
                continue
            start, end = [x.strip().split(" ")[0] for x in line.split("-->")]
            clean = [t for t in lines[i + 1:] if "<" not in t]
            body = " ".join(clean).strip()
            body = TAG_RE.sub("", body).strip()
            if body:
                segs.append(Segment(_ts(start), _ts(end), body))
    merged: list[Segment] = []
    for s in segs:
        if merged and merged[-1].text == s.text:
            merged[-1].end = s.end
        else:
            merged.append(s)
    return merged


def parse_chat_jsonl(text: str) -> list[ChatMessage]:
    """yt-dlp live_chat JSON(줄 단위)에서 텍스트 메시지만 뽑는다."""
    out: list[ChatMessage] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        rp = obj.get("replayChatItemAction", {})
        offset = int(rp.get("videoOffsetTimeMsec", "0") or 0) / 1000
        for action in rp.get("actions", []):
            renderer = action.get("addChatItemAction", {}).get("item", {}).get(
                "liveChatTextMessageRenderer")
            if not renderer:
                continue
            runs = renderer.get("message", {}).get("runs", [])
            msg = "".join(r.get("text", "") for r in runs)
            author = renderer.get("authorName", {}).get("simpleText", "")
            out.append(ChatMessage(offset, author, msg))
    return out


def anonymize(chat: list[ChatMessage]) -> None:
    """작성자를 빈도순 익명 ID(U001...)로 바꾼다. 원본 닉네임은 결과에 남기지 않는다."""
    counts = collections.Counter(m.author for m in chat)
    ids = {a: f"U{i + 1:03d}" for i, (a, _) in enumerate(counts.most_common())}
    for m in chat:
        m.author_id = ids[m.author]
        m.author = ""


def classify(msg: str) -> str:
    for name, pat in CHAT_CATEGORIES:
        if re.search(pat, msg):
            return name
    return CHAT_OTHER


def extract_nouns(text: str, kiwi, stop: set[str]) -> list[str]:
    text = re.sub(r":[a-z_]+:", "", text)
    return [
        tok.form for tok in kiwi.tokenize(text)
        if tok.tag in ("NNG", "NNP") and len(tok.form) >= 2 and tok.form not in stop
    ]


def analyze(segments: list[Segment], chat: list[ChatMessage], kiwi, *,
            window_sec: int = 60, top_n: int = 45, min_edge: int = 3,
            stop: set[str] | None = None) -> AnalysisResult:
    stop = DEFAULT_STOP if stop is None else stop
    res = AnalysisResult(segments=segments, chat=chat)

    # 1) 핵심어 빈도
    seg_nouns = []
    for s in segments:
        text = TAG_RE.sub("", s.text)
        seg_nouns.append((s.start, extract_nouns(text, kiwi, stop)))
    freq = collections.Counter(n for _, ns in seg_nouns for n in ns)
    res.term_freq = freq.most_common(25)

    # 2) 공출현 네트워크 (window 단위, 상위 명사, 최소 공출현 횟수)
    windows: dict[int, set[str]] = collections.defaultdict(set)
    for start, ns in seg_nouns:
        windows[int(start // window_sec)].update(ns)
    top = [w for w, _ in freq.most_common(top_n)]
    top_set = set(top)
    pair = collections.Counter()
    for ns in windows.values():
        for a, b in itertools.combinations(sorted(ns & top_set), 2):
            pair[(a, b)] += 1
    G = nx.Graph()
    for w in top:
        G.add_node(w, freq=freq[w])
    for (a, b), c in pair.items():
        if c >= min_edge:
            G.add_edge(a, b, weight=c)
    G.remove_nodes_from([n for n in list(G.nodes) if G.degree(n) == 0])
    if G.number_of_nodes():
        bet = nx.betweenness_centrality(G, weight=None)
        comms = list(nx_community.greedy_modularity_communities(G, weight="weight"))
        cid = {n: i for i, c in enumerate(comms) for n in c}
        res.graph_nodes = [
            {"id": n, "freq": G.nodes[n]["freq"], "community": cid.get(n, -1),
             "betweenness": round(bet.get(n, 0.0), 4)} for n in G.nodes]
        res.graph_edges = [{"source": a, "target": b, "weight": d["weight"]}
                           for a, b, d in G.edges(data=True)]
        res.communities = [sorted(c) for c in comms]

    # 3) 채팅 참여 유형
    for m in chat:
        m.category = classify(m.text)
    cats = collections.Counter(m.category for m in chat)
    res.category_counts = cats.most_common()

    # 4) 분 단위 시계열
    per_min: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    for m in chat:
        per_min[int(m.t // 60)][m.category] += 1
    res.per_minute = {k: dict(v) for k, v in sorted(per_min.items())}

    sale_seg = collections.Counter()
    for start, ns in seg_nouns:
        if {"구매", "판매", "완판", "한정", "가격", "주문"} & set(ns):
            sale_seg[int(start // 60)] += 1
    res.sale_talk_per_minute = dict(sorted(sale_seg.items()))

    # 5) 판매 발화와 판매 반응의 상관 (분 단위)
    if chat and segments:
        last = int(max(max(s.end for s in segments), max(m.t for m in chat)) // 60)
        xs, ys = [], []
        for k in range(last + 1):
            xs.append(sale_seg.get(k, 0))
            c = per_min.get(k, collections.Counter())
            ys.append(c["구매 언급"] + c["판매 응원(완판)"])
        if len(set(xs)) > 1 and len(set(ys)) > 1:
            n = len(xs)
            mx, my = sum(xs) / n, sum(ys) / n
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            sx = sum((x - mx) ** 2 for x in xs) ** 0.5
            sy = sum((y - my) ** 2 for y in ys) ** 0.5
            res.correlation = round(cov / (sx * sy), 3)
    return res


def chat_quotes_check(chat: list[ChatMessage], quotes: list[str]) -> list[dict]:
    """인용 문구가 채팅에 있는지 공백을 무시하고 확인한다."""
    out = []
    norm = [(m.t, m.text.replace(" ", "")) for m in chat]
    for q in quotes:
        key = q.replace(" ", "")
        hits = [t for t, s in norm if key in s]
        out.append({"quote": q, "count": len(hits),
                    "first_sec": min(hits) if hits else None})
    return out
