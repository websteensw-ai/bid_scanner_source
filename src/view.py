"""분석 결과를 화면용 딕셔너리로 바꾼다. 테스트 결과와 실제 결과가 같은 모양을 쓴다."""
from __future__ import annotations

from src.pipeline import AnalysisResult, CHAT_OTHER

CATS = ["팬덤 응원", "판매 응원(완판)", "진행 요청", "감각적 반응", "상품 선호", "구매 언급", "지역·축제 관심", CHAT_OTHER]


def result_to_view(res: AnalysisResult, title: str, duration_min: float, quotes: list[dict]) -> dict:
    cats = dict(res.category_counts)
    per_min_cat = {str(k): v for k, v in res.per_minute.items()}
    return {
        "video_title": title,
        "duration_min": duration_min,
        "note": "실제 분석 결과입니다. 채팅 작성자는 익명 ID로 표시됩니다.",
        "n_segments": len(res.segments),
        "chat": {
            "n_msgs": len(res.chat),
            "n_authors": len({m.author_id for m in res.chat}),
            "cats": [[c, cats.get(c, 0)] for c in CATS if cats.get(c)],
            "per_min_cat": per_min_cat,
            "sale_talk_min": [[k, v] for k, v in res.sale_talk_per_minute.items()],
            "chat_nouns": [],
        },
        "terms": [{"term": t, "freq": f, "community": -1} for t, f in res.term_freq],
        "network": {"nodes": res.graph_nodes, "edges": res.graph_edges, "communities": res.communities},
        "sections": {},
        "quotes": quotes,
        "correlation": res.correlation,
    }
