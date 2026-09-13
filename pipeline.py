import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Callable, Optional
from collectors.bizinfo_collector import BizInfoCollector
from collectors.iris_collector import IrisCollector
from collectors.kstartup_collector import KStartupCollector
from collectors.g2b_collector import G2BCollector
from extractors.doc_parser import DocumentParser
from analyzers.llm_evaluator import LLMEvaluator, REPORT_FIELDS, NA

# 수집 출처 레지스트리: 웹 폼/CLI에서 선택 가능한 키 -> (표시 라벨, 수집기 클래스)
SOURCE_REGISTRY = {
    "bizinfo": {"label": "기업마당", "collector": BizInfoCollector},
    "iris": {"label": "IRIS (범부처통합연구지원시스템)", "collector": IrisCollector},
    "kstartup": {"label": "K-Startup", "collector": KStartupCollector},
    "g2b": {"label": "나라장터", "collector": G2BCollector},
}

QUICK_FILTER_BATCH_SIZE = 20
MAX_WORKERS = 5

ProgressCallback = Callable[[str, int, int], None]


def run_pipeline(
    days: int,
    min_score: int,
    keywords: Optional[List[str]] = None,
    business_profile: Optional[Dict[str, str]] = None,
    sources: Optional[List[str]] = None,
    progress_cb: Optional[ProgressCallback] = None,
) -> List[Dict[str, Any]]:
    """공고 수집 -> 문서 파싱 -> LLM 심층 평가 파이프라인을 실행하고 선별된 결과 리스트를 반환

    keywords/business_profile을 지정하지 않으면 기본(AX) 설정을 사용한다.
    sources는 SOURCE_REGISTRY의 키 목록으로 수집 대상을 제한한다 (None/빈 리스트면 전체 사용).
    progress_cb(stage, current, total)은 각 단계 진행 상황을 외부(웹앱 등)에 알리기 위한 훅.
    """

    def report(stage: str, current: int = 0, total: int = 0):
        if progress_cb:
            progress_cb(stage, current, total)

    selected_keys = [key for key in sources if key in SOURCE_REGISTRY] if sources else list(SOURCE_REGISTRY)
    if not selected_keys:
        selected_keys = list(SOURCE_REGISTRY)
    collector_classes = [SOURCE_REGISTRY[key]["collector"] for key in selected_keys]

    print(f"=== [1/3] 최근 {days}일 공고 수집 시작 ({', '.join(selected_keys)}) ===")
    raw_notices = []
    seen_titles = set()
    for idx, collector_cls in enumerate(collector_classes, 1):
        report(f"{collector_cls.__name__} 수집 중", idx, len(collector_classes))
        collector = collector_cls(keywords=keywords) if keywords else collector_cls()
        for notice in collector.fetch_recent_notices(days=days):
            if notice["title"] in seen_titles:
                continue
            seen_titles.add(notice["title"])
            raw_notices.append(notice)
    print(f"-> 1차 키워드 필터링 통과 공고: {len(raw_notices)}건")

    evaluator = LLMEvaluator(business_profile=business_profile)

    print("\n=== [2/3] 1차 빠른 스크리닝 (제목/요약, 문서 파싱 없음) ===")
    candidates = []
    for i in range(0, len(raw_notices), QUICK_FILTER_BATCH_SIZE):
        batch = raw_notices[i:i + QUICK_FILTER_BATCH_SIZE]
        report("1차 스크리닝 중", i + len(batch), len(raw_notices))
        flags = evaluator.quick_filter(batch)
        candidates.extend(n for n, keep in zip(batch, flags) if keep)
    print(f"-> 1차 스크리닝 통과 (심층평가 대상): {len(candidates)}건 / {len(raw_notices)}건")

    print("\n=== [3/3] 세부 문서 파싱 및 LLM 심층 평가 (병렬) ===")
    evaluated_results = []
    progress_lock = threading.Lock()
    done_count = 0

    def process(notice: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        nonlocal done_count
        doc_text = ""
        for att_path in notice.get("attachment_paths", []):
            doc_text += DocumentParser.extract_text(att_path) + "\n"

        analysis = evaluator.evaluate(notice, doc_content=doc_text)

        with progress_lock:
            done_count += 1
            report("LLM 심층 평가 중", done_count, len(candidates))

        score = analysis.get("relevance_score", 0)
        if not (analysis.get("is_relevant") and score >= min_score):
            return None

        result = {
            "title": notice["title"],
            "pub_date": notice.get("pub_date"),
            "relevance_score": score,
            "url": notice.get("url"),
        }
        for field in REPORT_FIELDS:
            result[field] = analysis.get(field) or NA
        return result

    if candidates:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = [pool.submit(process, notice) for notice in candidates]
            for future in as_completed(futures):
                result = future.result()
                if result:
                    evaluated_results.append(result)

    print(f"-> 최종 선별된 고연관성 공고: {len(evaluated_results)}건")
    return evaluated_results
