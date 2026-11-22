"""초기 사고역량 진단 · 학습자 프로파일 · 적응형 학습 추천 (지식자산 기본계획 ⅩⅤ장 13~22절).

④ 학습자 성장 DB 는 LearnerState.think 에 JSON 으로 담는다 (ThinkState).
추천의 목표는 사용시간이 아니라 사고역량 향상이다 (28절) — 그래서 1순위는 취약 역량, 학생 흥미는 4순위다 (17절).
"""
import json
import re
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from src.think.kb import KnowledgeBase, Topic, knowledge


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Diagnosis(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    choice: str = ""                           # D3 에서 고른 입장
    levels: dict[str, int] = Field(default_factory=dict)
    evidence: dict[str, str] = Field(default_factory=dict)
    note: str = ""
    evaluator: str = "demo"
    ts: str = Field(default_factory=now)


class HistoryItem(BaseModel):
    topic: str
    archetypes: list[str]
    conflicts: list[str]
    form: str
    level: int
    path: str                                  # recommended / interest / explore
    first_thought: str = ""                    # B형: 독서 전 독립적 최초사고
    result: dict[str, int] = Field(default_factory=dict)   # 학습 후 역량 판정 (표준 성취평가 연결 지점)
    started_at: str = Field(default_factory=now)
    finished_at: str | None = None


class ThinkState(BaseModel):
    profile: dict[str, int] = Field(default_factory=dict)  # 역량 id → 1~5
    diagnoses: list[Diagnosis] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    history: list[HistoryItem] = Field(default_factory=list)

    @property
    def diagnosed(self) -> bool:
        return bool(self.profile)


# ====================================================================== 진단 채점
_REASON = re.compile(r"왜냐하면|때문|이므로|므로|그래서|따라서|근거|이유")
_DEFINE = re.compile(r"(이)?란\b|라는 것은|뜻한다|의미|정의|구별|다르다|같지 않")
_COUNTER = re.compile(r"반대|반면|하지만|그러나|물론|다른 입장|상대|반론|라고 볼 수도")
_REBUT = re.compile(r"그렇더라도|그럼에도|그래도|오히려|다시 말해|반박|하지만 그")
_REVISE = re.compile(r"다만|수정|고쳐|바뀌|생각해 보니|조건|경우에 따라|일부")
_EXAMPLE = re.compile(r"예를 들어|예컨대|가령|만약|경우")


def _lv(score: float) -> int:
    return max(1, min(5, round(score)))


def demo_diagnose(kb: KnowledgeBase, answers: dict[str, str], choice: str) -> Diagnosis:
    """키 없는 환경용 규칙 기반 판정 (표시 신호만 본다 — 실제 운영은 LLM 판정 + 교사 확인)."""
    a1, a2, a3 = (answers.get(k, "") for k in ("D1", "D2", "D3"))
    allt = " ".join([a1, a2, a3])

    def base(t: str) -> float:
        n = len(t.strip())
        return 1 if n < 15 else 2 if n < 60 else 3 if n < 160 else 3.5

    lv = {
        "understand": base(a1) + (0.5 if re.search(r"공정|똑같", a1) else 0) + (0.5 if _EXAMPLE.search(a1) else 0),
        "define": base(a1) - 0.5 + (1.5 if _DEFINE.search(a1) else 0),
        "reason": base(a2) - 0.5 + (1 if _REASON.search(allt) else 0) + (0.5 if _EXAMPLE.search(allt) else 0),
        "respond": base(a2) + (0.5 if "?" in allt or _EXAMPLE.search(a2) else 0),
        "counter": 1 + (1.5 if _COUNTER.search(a2) else 0) + (1 if _COUNTER.search(a3) else 0),
        "rebut": 1 + (1.5 if _REBUT.search(a3) else 0) + (0.5 if choice and len(a3) > 80 else 0),
        "revise": 1.5 + (1.5 if _REVISE.search(allt) else 0),
    }
    levels = {c: _lv(lv.get(c, 2)) for c in kb.competencies.ids()}
    ev = {}
    for c, rx in (("define", _DEFINE), ("reason", _REASON), ("counter", _COUNTER), ("rebut", _REBUT), ("revise", _REVISE)):
        m = rx.search(allt)
        if m:
            s = max(0, m.start() - 20)
            ev[c] = allt[s:m.end() + 30].strip()
    return Diagnosis(answers=answers, choice=choice, levels=levels, evidence=ev, evaluator="demo",
                     note="규칙 기반 예비 판정이에요. 선생님 확인 전까지는 참고용이에요.")


class LLMDiagnoser:
    def __init__(self, provider):
        self.provider = provider

    def __call__(self, kb: KnowledgeBase, answers: dict[str, str], choice: str) -> Diagnosis:
        comps = [c.model_dump() for c in kb.competencies.items]
        system = ("너는 고등학생의 사고역량을 진단하는 평가자다. 성적이 아니라 현재 사고 프로파일을 파악한다. "
                  "지식의 양이 아니라 사고의 방식(정의·추론·반론 이해·재반론·자기수정)을 학생 글의 근거로만 판단한다. "
                  "역량마다 1~5 수준과 근거가 된 학생 문장(그대로 인용)을 준다. 근거가 없으면 2 이하로 둔다. "
                  'JSON 하나만: {"levels": {"역량id": 1~5}, "evidence": {"역량id": "인용"}, "note": "학생에게 보일 한 문장(~요체)"}')
        user = json.dumps({"competencies": comps, "levels": kb.competencies.levels,
                           "tasks": kb.diagnostic["tasks"], "answers": answers, "choice": choice}, ensure_ascii=False)
        raw = self.provider._complete(system, user, max_tokens=2500, effort="medium")
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        d = json.loads(m.group(0)) if m else {}
        levels = {c: _lv(float(d.get("levels", {}).get(c, 2))) for c in kb.competencies.ids()}
        return Diagnosis(answers=answers, choice=choice, levels=levels, evidence=d.get("evidence", {}) or {},
                         note=str(d.get("note", "")), evaluator=f"ai:{getattr(self.provider, 'model', '')}")


# ====================================================================== 추천
class Recommendation(BaseModel):
    topic: Topic
    score: float
    parts: dict[str, float]
    reasons: list[str]
    path: str


class Adaptive:
    def __init__(self, ts: ThinkState, kb: KnowledgeBase | None = None):
        self.ts = ts
        self.kb = kb or knowledge()
        self.w = self.kb.diagnostic["weights"]

    # ---------- 프로파일 ----------
    def apply_diagnosis(self, d: Diagnosis) -> None:
        self.ts.diagnoses.append(d)
        self.ts.profile = dict(d.levels)

    def average(self) -> float:
        p = self.ts.profile
        return sum(p.values()) / len(p) if p else 0.0

    def overall(self) -> str:
        return self.kb.competencies.overall_of(self.average()) if self.ts.profile else "미진단"

    def strengths(self, n: int = 2) -> list[str]:
        return [c for c, _ in sorted(self.ts.profile.items(), key=lambda x: -x[1])[:n]]

    def weaknesses(self, n: int = 2) -> list[str]:
        return [c for c, _ in sorted(self.ts.profile.items(), key=lambda x: x[1])[:n]]

    # ---------- 반복 방지 (19절) ----------
    def _done(self) -> dict[str, int]:
        """사고원형 → 지금까지 다룬 최고 난이도."""
        out: dict[str, int] = {}
        for h in self.ts.history:
            for a in h.archetypes:
                out[a] = max(out.get(a, 0), h.level)
        return out

    def eligible(self) -> list[Topic]:
        done_topics = {h.topic for h in self.ts.history}
        done = self._done()
        out = []
        for t in self.kb.approved_topics():
            if t.id in done_topics:
                continue
            # 같은 사고원형을 다시 할 때는 더 높은 난이도로만 (새 상황·더 깊은 사고)
            if any(a in done and t.level <= done[a] for a in t.archetypes):
                continue
            out.append(t)
        return out

    # ---------- 점수 (18절) ----------
    def score(self, t: Topic, *, use_interest: bool = True) -> tuple[float, dict[str, float], list[str]]:
        p = self.ts.profile
        names = self.kb.competencies.name
        weak = sum((5 - p.get(a, 3)) / 4 for a in t.abilities) / len(t.abilities)
        target = min(5.0, self.average() + 0.5)                 # 지금보다 조금 높은 수준 (근접 발달 영역)
        diff = 1 - abs(t.level - target) / 4
        done = self._done()
        unexplored = 1.0 if not any(a in done for a in t.archetypes) else 0.3
        concepts, fields = self.kb.topic_concepts(t), self.kb.topic_fields(t)
        interest = 1.0 if use_interest and (set(self.ts.interests) & (concepts | fields)) else 0.0
        recent = self.ts.history[-3:]
        rc = {c for h in recent for c in h.conflicts}
        diversity = 1 - len(self.kb.topic_conflicts(t) & rc) / max(1, len(self.kb.topic_conflicts(t)))
        last = self.ts.history[-1] if self.ts.history else None
        link = 1.0 if last and (set(last.conflicts) & self.kb.topic_conflicts(t)) and t.level > last.level else 0.0
        parts = {"weak": weak, "difficulty": diff, "unexplored": unexplored, "interest": interest,
                 "diversity": diversity, "link": link}
        total = sum(self.w[k] * v for k, v in parts.items())
        reasons = []
        hit = [a for a in t.abilities if a in self.weaknesses(3)]
        if hit:
            reasons.append("보완 영역 훈련: " + "·".join(names(a) for a in hit))
        if diff >= 0.75:
            reasons.append(f"지금 수준에 맞는 난이도 (Level {t.level})")
        if unexplored == 1.0:
            reasons.append("아직 다뤄 보지 않은 사고원형")
        if interest:
            reasons.append("관심 주제와 연결")
        if link:
            reasons.append("지난 학습을 한 단계 깊게")
        return round(total, 3), {k: round(v, 2) for k, v in parts.items()}, reasons

    def recommend(self, path: str = "recommended", interest: str | None = None, n: int = 3) -> list[Recommendation]:
        pool = self.eligible()
        if path == "interest" and interest:
            pool = [t for t in pool if interest in (self.kb.topic_concepts(t) | self.kb.topic_fields(t))
                    or any(interest in self.kb.archetype(a).question for a in t.archetypes)] or pool
        if path == "explore":
            known = {c for h in self.ts.history for c in h.conflicts}
            fav = set(self.ts.interests)
            pool = [t for t in pool if not (self.kb.topic_conflicts(t) & known)
                    and not ((self.kb.topic_concepts(t) | self.kb.topic_fields(t)) & fav)] or pool
        recs = []
        for t in pool:
            s, parts, why = self.score(t, use_interest=(path == "recommended"))
            if path == "explore":
                s = round(0.6 * parts["unexplored"] + 0.4 * parts["difficulty"], 3)
                why = ["평소 관심과 다른 분야 (사고의 편식 방지)"] + [r for r in why if "난이도" in r]
            recs.append(Recommendation(topic=t, score=s, parts=parts, reasons=why, path=path))
        recs.sort(key=lambda r: (-r.score, r.topic.level, r.topic.id))
        return recs[:n]

    def most_needed(self) -> Recommendation | None:
        r = self.recommend("recommended", n=1)
        return r[0] if r else None

    # ---------- 학습 시작·기록 ----------
    def start(self, topic_id: str, path: str) -> HistoryItem:
        t = self.kb.topic(topic_id)
        if t is None or t.review != "approved":
            raise ValueError("추천할 수 없는 논제예요.")
        h = HistoryItem(topic=t.id, archetypes=t.archetypes, conflicts=sorted(self.kb.topic_conflicts(t)),
                        form=t.form, level=t.level, path=path)
        self.ts.history.append(h)
        return h

    def current(self) -> HistoryItem | None:
        return next((h for h in reversed(self.ts.history) if h.finished_at is None), None)

    def save_first_thought(self, topic_id: str, text: str) -> HistoryItem:
        h = next((h for h in reversed(self.ts.history) if h.topic == topic_id), None)
        if h is None:
            raise ValueError("시작하지 않은 논제예요.")
        h.first_thought = text.strip()
        return h


# ====================================================================== AI 1차 구조화 (23절)
STRUCTURE_FIELDS = ["asset_type", "era", "region", "fields", "persons", "concepts", "claim", "counter_claim",
                    "hidden_premise", "counterexamples", "conflicts", "universal_question", "archetypes",
                    "level", "abilities", "cross_links"]


def structure_draft(kb: KnowledgeBase, title: str, text: str, provider=None) -> dict:
    """원문 한 편 → 사고구조 메타데이터 초안. 핵심 명제·대립 명제·사고원형·가치충돌은 반드시 전문가 검수 (23절 2단계)."""
    if provider is not None:
        system = ("너는 고전평론·명저평론·칼럼을 교육용 사고훈련 자산으로 구조화하는 분석가다. "
                  "문서 자체가 아니라 그 안의 핵심 개념·명제·대립 명제·숨은 전제·반례·가치충돌·보편적 질문을 뽑는다. "
                  "가치충돌은 'A vs B' 형식. 사고원형은 특정 사건을 넘어 반복 적용되는 질문 형태. "
                  "asset_type 은 concept·choice·policy·history·literature 중 하나, "
                  f"abilities 는 {kb.competencies.ids()} 중에서. level 은 자료 기본 난이도 1~5. "
                  "cross_links 는 아래 기존 사고원형 id 중 결합 가능한 것. 원문에 없는 내용은 지어내지 말고 빈 값으로 둔다. "
                  f"JSON 하나만, 키: {STRUCTURE_FIELDS}")
        user = json.dumps({"title": title, "text": text[:12000],
                           "existing_archetypes": [{"id": a.id, "question": a.question} for a in kb.archetypes]},
                          ensure_ascii=False)
        raw = provider._complete(system, user, max_tokens=4000, effort="medium")
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        d = json.loads(m.group(0)) if m else {}
        d["_by"] = f"ai:{getattr(provider, 'model', '')}"
    else:
        known = sorted({c for a in kb.archetypes for c in a.concepts} | {c for s in kb.sources for c in s.concepts})
        found = [c for c in known if c in text]
        conflicts = [c for a in kb.archetypes for c in a.conflicts if all(x.strip() in text for x in c.split(" vs "))]
        d = {k: "" for k in STRUCTURE_FIELDS}
        d.update({"concepts": found, "conflicts": sorted(set(conflicts)),
                  "cross_links": [a.id for a in kb.archetypes if set(a.concepts) & set(found)],
                  "universal_question": next((s.strip() + "?" for s in re.split(r"[?？]", text) if s.strip().endswith(("가", "까", "는가"))), ""),
                  "_by": "demo (키워드 대조 — 실제 구조화는 AI 연결 후)"})
    d["title"] = title
    d["review"] = {"status": "draft", "must_review": ["claim", "counter_claim", "archetypes", "conflicts", "cross_links"]}
    return d
