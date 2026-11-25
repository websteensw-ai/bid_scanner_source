"""지식자산·사고원형 DB 로더와 지식 그래프 (지식자산 기본계획 ⅩⅤ장).

네 가지 핵심 DB (25절)
  ① 원천 지식자산 DB   content/knowledge/sources.yaml + pilot/*.yaml (책 단위 시범 묶음)
  ② 사고원형 DB         content/knowledge/archetypes.yaml
  ③ 논제·제시문 DB      content/knowledge/topics.yaml
  ④ 학습자 성장 DB      LearnerState.think (학생별 프로파일·이력, src/think/adaptive.py)

분류의 기본 단위는 문서가 아니라 문서 안의 개념·명제·가치충돌·사고원형이다 (2절).
그래서 자료 → 개념 → 가치충돌 → 사고원형 → 논제 → 사고역량을 잇는 그래프로 읽는다 (10절).
"""
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[2] / "content" / "knowledge"

ASSET_TYPES = {"concept": "개념·명제형", "choice": "인물·선택·결과형", "policy": "정책·사회문제형",
               "history": "역사적 사례형", "literature": "문학·인간이해형"}
TOPIC_FORMS = {"dilemma": "딜레마", "comparison": "비교", "policy": "정책", "concept": "개념"}
MODES = {"A": "A형 독서 선행", "B": "B형 사고 선행", "C": "C형 탐구 발견"}
PUBLIC = {"full": "전문 제공", "summary": "요약만 제공", "none": "비공개"}
COPYRIGHT = {"own": "자체 저작", "public_domain": "퍼블릭도메인", "restricted": "제한 자료"}
# 50편 시범 DB 구성 (24절)
PILOT_QUOTA = {"철학": 10, "정치·법": 10, "인간관계·윤리": 10, "리더십·역사적 선택": 10, "과학·사회·문명": 10}


class Competency(BaseModel):
    id: str
    name: str
    desc: str = ""


class Competencies(BaseModel):
    version: str
    status: str = "draft"
    levels: dict[int, str]
    items: list[Competency]
    overall: list[dict]

    def ids(self) -> list[str]:
        return [c.id for c in self.items]

    def name(self, cid: str) -> str:
        return next((c.name for c in self.items if c.id == cid), cid)

    def overall_of(self, avg: float) -> str:
        return next(o["name"] for o in self.overall if avg <= float(o["max"]))


class Source(BaseModel):
    """원천 자료 1편 — 1차 메타데이터(문서·저작권 관리) + 2차 사고구조 메타데이터(출제·추천)."""
    id: str
    title: str
    source_type: str
    asset_type: Literal["concept", "choice", "policy", "history", "literature"]
    author: dict = Field(default_factory=dict)
    work: str = ""
    era: str = ""
    region: str = ""
    fields: list[str] = Field(default_factory=list)
    persons: list[str] = Field(default_factory=list)
    public: Literal["full", "summary", "none"] = "none"
    copyright: Literal["own", "public_domain", "restricted"] = "own"
    pilot_group: str = ""
    concepts: list[str] = Field(default_factory=list)
    claim: str = ""
    counter_claim: str = ""
    hidden_premise: str = ""
    counterexamples: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)      # 관계 태그 "A vs B"
    universal_question: str = ""
    situation: str = ""
    choice: str = ""
    tags: list[str] = Field(default_factory=list)
    location: str = ""                                      # 원문 위치 (내부 검증용 — 학생 화면에 싣지 않음)
    summary: str = ""                                       # 요약 (public 이 summary 일 때만 학생에게 제공 가능)
    review: dict = Field(default_factory=dict)              # {status: draft|sample|approved, reviewer}

    @model_validator(mode="after")
    def _conflicts(self):
        for c in self.conflicts:
            if " vs " not in c:
                raise ValueError(f"{self.id}: 가치충돌은 'A vs B' 형식이어야 해요 ({c})")
        return self


class Archetype(BaseModel):
    id: str
    question: str
    sources: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    positions: list[str] = Field(default_factory=list)
    counterexamples: list[str] = Field(default_factory=list)
    situations: list[str] = Field(default_factory=list)
    abilities: list[str] = Field(default_factory=list)
    level_range: tuple[int, int] = (1, 5)


class Topic(BaseModel):
    id: str
    archetypes: list[str]
    prompt: str
    form: Literal["dilemma", "comparison", "policy", "concept"]
    level: int = Field(ge=1, le=5)
    mode: Literal["A", "B", "C"] = "B"
    abilities: list[str]
    expected_turns: str = ""
    rebuttal: Literal["low", "mid", "high"] = "mid"
    cross: bool = False
    review: Literal["draft", "approved", "retired"] = "draft"


class KnowledgeBase(BaseModel):
    competencies: Competencies
    sources: list[Source]
    archetypes: list[Archetype]
    topics: list[Topic]
    diagnostic: dict

    @model_validator(mode="after")
    def _refs(self):
        src, arc, comp = {s.id for s in self.sources}, {a.id for a in self.archetypes}, set(self.competencies.ids())
        if len(src) != len(self.sources) or len(arc) != len(self.archetypes) or len({t.id for t in self.topics}) != len(self.topics):
            raise ValueError("ID 가 중복됩니다")
        for a in self.archetypes:
            if bad := set(a.sources) - src:
                raise ValueError(f"{a.id}: 없는 자료 {sorted(bad)}")
            if bad := set(a.abilities) - comp:
                raise ValueError(f"{a.id}: 없는 역량 {sorted(bad)}")
        for t in self.topics:
            if bad := set(t.archetypes) - arc:
                raise ValueError(f"{t.id}: 없는 사고원형 {sorted(bad)}")
            if bad := set(t.abilities) - comp:
                raise ValueError(f"{t.id}: 없는 역량 {sorted(bad)}")
            if t.cross != (len(t.archetypes) > 1):
                raise ValueError(f"{t.id}: 교차출제(cross)는 사고원형이 2개 이상일 때만 true")
        for task in self.diagnostic.get("tasks", []):
            if bad := set(task["measures"]) - comp:
                raise ValueError(f"진단 {task['id']}: 없는 역량 {sorted(bad)}")
        return self

    # ---------- 조회 ----------
    def source(self, sid: str) -> Source:
        return next(s for s in self.sources if s.id == sid)

    def archetype(self, aid: str) -> Archetype:
        return next(a for a in self.archetypes if a.id == aid)

    def topic(self, tid: str) -> Topic | None:
        return next((t for t in self.topics if t.id == tid), None)

    def topics_for(self, aid: str) -> list[Topic]:
        return [t for t in self.topics if aid in t.archetypes]

    def approved_topics(self) -> list[Topic]:
        return [t for t in self.topics if t.review == "approved"]

    def topic_conflicts(self, t: Topic) -> set[str]:
        return {c for a in t.archetypes for c in self.archetype(a).conflicts}

    def topic_concepts(self, t: Topic) -> set[str]:
        return {c for a in t.archetypes for c in self.archetype(a).concepts}

    def topic_fields(self, t: Topic) -> set[str]:
        return {f for a in t.archetypes for s in self.archetype(a).sources for f in self.source(s).fields}

    # ---------- 지식 그래프 (10절) ----------
    def graph(self) -> dict[str, set[str]]:
        """노드 'kind:이름' → 이웃. 자료·인물·저작·개념·가치충돌·사고원형·논제·역량."""
        g: dict[str, set[str]] = defaultdict(set)

        def link(a: str, b: str) -> None:
            g[a].add(b)
            g[b].add(a)

        for s in self.sources:
            n = f"source:{s.id}"
            for p in s.persons:
                link(n, f"person:{p}")
            if s.work:
                link(n, f"work:{s.work}")
            for c in s.concepts:
                link(n, f"concept:{c}")
            for c in s.conflicts:
                link(n, f"conflict:{c}")
                for side in c.split(" vs "):
                    link(f"conflict:{c}", f"concept:{side.strip()}")
        for a in self.archetypes:
            n = f"archetype:{a.id}"
            for s in a.sources:
                link(n, f"source:{s}")
            for c in a.conflicts:
                link(n, f"conflict:{c}")
            for c in a.concepts:
                link(n, f"concept:{c}")
            for ab in a.abilities:
                link(n, f"ability:{ab}")
        for t in self.topics:
            n = f"topic:{t.id}"
            for a in t.archetypes:
                link(n, f"archetype:{a}")
            for ab in t.abilities:
                link(n, f"ability:{ab}")
        return g

    def source_map(self, sid: str) -> list[dict]:
        """자료 하나에서 출발한 사고의 지도: 자료 → 가치충돌 → 사고원형 → 논제 → 훈련 역량."""
        out = []
        for a in self.archetypes:
            if sid not in a.sources:
                continue
            out.append({"archetype": a, "conflicts": a.conflicts,
                        "topics": self.topics_for(a.id),
                        "abilities": [self.competencies.name(x) for x in a.abilities]})
        return out

    def cross_candidates(self) -> list[tuple[Archetype, Archetype, set[str]]]:
        """교차출제 후보 (11절): 개념을 공유하지만 출처가 다른 두 사고원형."""
        out = []
        arcs = self.archetypes
        for i, a in enumerate(arcs):
            for b in arcs[i + 1:]:
                shared = (set(a.concepts) | {x for c in a.conflicts for x in c.split(" vs ")}) & \
                         (set(b.concepts) | {x for c in b.conflicts for x in c.split(" vs ")})
                if set(a.sources) != set(b.sources) and shared:
                    out.append((a, b, shared))
        return out

    # ---------- 구축 현황 (24절) ----------
    def pilot_progress(self) -> list[dict]:
        done, draft = defaultdict(int), defaultdict(int)
        for s in self.sources:
            st = s.review.get("status")
            if st == "approved":
                done[s.pilot_group] += 1
            elif st == "draft":
                draft[s.pilot_group] += 1
        return [{"group": g, "target": n, "done": done.get(g, 0), "draft": draft.get(g, 0)} for g, n in PILOT_QUOTA.items()]

    def stats(self) -> dict:
        return {"sources": len(self.sources), "archetypes": len(self.archetypes), "topics": len(self.topics),
                "approved_topics": len(self.approved_topics()),
                "by_type": {ASSET_TYPES[k]: sum(1 for s in self.sources if s.asset_type == k) for k in ASSET_TYPES},
                "conflicts": sorted({c for s in self.sources for c in s.conflicts} | {c for a in self.archetypes for c in a.conflicts})}


def _read(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def _pilot() -> dict[str, list]:
    """시범 DB 묶음 (content/knowledge/pilot/*.yaml) — 책 한 권 단위로 sources·archetypes·topics 를 함께 담는다."""
    out: dict[str, list] = {"sources": [], "archetypes": [], "topics": []}
    for f in sorted((ROOT / "pilot").glob("*.yaml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for k in out:
            out[k] += d.get(k) or []
    return out


@lru_cache
def knowledge() -> KnowledgeBase:
    extra = _pilot()
    return KnowledgeBase(competencies=Competencies.model_validate(_read("competencies.yaml")),
                         sources=[Source.model_validate(x) for x in _read("sources.yaml")["items"] + extra["sources"]],
                         archetypes=[Archetype.model_validate(x) for x in _read("archetypes.yaml")["items"] + extra["archetypes"]],
                         topics=[Topic.model_validate(x) for x in _read("topics.yaml")["items"] + extra["topics"]],
                         diagnostic=_read("diagnostic.yaml"))


@lru_cache
def catalog() -> list[dict]:
    """원천 자료 목록 (content/knowledge/catalog/*.yaml): 책별 전체 편 목록. 구조화 여부는 SRC-<접두어> 로 센다."""
    kb = knowledge()
    out = []
    for f in sorted((ROOT / "catalog").glob("*.yaml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        book = d.get("book")
        title = book.get("title", "") if isinstance(book, dict) else str(book or f.stem)
        prefix = f.stem.split("_")[0]
        pieces = d.get("pieces") or []
        src = [s for s in kb.sources if s.id.startswith(f"SRC-{prefix}")]
        out.append({"key": f.stem, "title": title.split(" — ")[0].split(" (")[0], "pieces": pieces,
                    "count": int(d.get("piece_count") or len(pieces)),
                    "classified": sum(1 for x in pieces if x.get("asset_type_guess") or x.get("pilot_group_guess")),
                    "structured": len(src),
                    "approved": sum(1 for s in src if s.review.get("status") == "approved")})
    return out


def inventory() -> dict:
    """원천 지식자산 전체 현황: 보유 → 목록 등재 → 1차 분류 → 2차 사고구조화 → 전문가 검수 (기본계획 23·24절)."""
    books = catalog()
    groups: dict[str, int] = defaultdict(int)
    types: dict[str, int] = defaultdict(int)
    for b in books:
        for x in b["pieces"]:
            if x.get("pilot_group_guess"):
                groups[x["pilot_group_guess"]] += 1
            if x.get("asset_type_guess") in ASSET_TYPES:
                types[ASSET_TYPES[x["asset_type_guess"]]] += 1
    return {"books": books, "total": sum(b["count"] for b in books),
            "classified": sum(b["classified"] for b in books),
            "structured": sum(b["structured"] for b in books),
            "approved": sum(b["approved"] for b in books),
            "groups": dict(sorted(groups.items(), key=lambda x: -x[1])), "types": dict(types)}


if __name__ == "__main__":       # python -m src.think.kb : 형식·참조 검사와 50편 구축 현황
    kb = knowledge()
    print("검사 통과:", kb.stats())
    for p in kb.pilot_progress():
        print(f"  {p['group']}: 검수 완료 {p['done']} + 초안 {p['draft']} / {p['target']}")
    for b in catalog():
        print(f"  {b['title']}: 목록 {b['count']}편 · 구조화 {b['structured']}편")
