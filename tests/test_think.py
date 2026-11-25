"""지식자산·사고원형 DB와 적응형 추천 (지식자산 기본계획 ⅩⅤ장)."""
import pytest
from fastapi.testclient import TestClient

from src.think.adaptive import Adaptive, HistoryItem, ThinkState, demo_diagnose, structure_draft
from src.think.kb import KnowledgeBase, Source, knowledge
from web import store as store_mod
from web.main import app

KB = knowledge()

ANS = {
    "D1": "공정은 모두를 똑같이 대하는 것이 아니다. 왜냐하면 처지가 다른 사람을 똑같이 대하면 오히려 불리해지기 때문이다. 예를 들어 다리가 불편한 사람에게 같은 계단을 요구할 수는 없다.",
    "D2": "희생할 수 없다고 생각한다. 사람을 수단으로 쓰면 안 되기 때문이다. 하지만 반대 입장은 더 많은 생명을 구하는 것이 옳다고 말할 것이다.",
    "D3": "B가 더 설득력 있다. A는 집단 판단이 오류가 적다고 하지만, 그럼에도 다수가 함께 틀린 역사가 있다. 다만 전문가 합의처럼 근거가 있는 경우는 조건에 따라 믿을 수 있다고 수정하겠다.",
}


def test_kb_loads_and_validates_references():
    st = KB.stats()
    assert st["sources"] >= 3 and st["archetypes"] >= 5 and st["approved_topics"] >= 5
    assert all(" vs " in c for c in st["conflicts"])
    assert [p["group"] for p in KB.pilot_progress()] == ["철학", "정치·법", "인간관계·윤리", "리더십·역사적 선택", "과학·사회·문명"]
    with pytest.raises(ValueError):
        Source(id="X", title="t", source_type="고전평론", asset_type="concept", conflicts=["진리와 설득"])
    bad = KB.model_dump()
    bad["topics"][0]["archetypes"] = ["ARC-999"]
    with pytest.raises(ValueError):
        KnowledgeBase.model_validate(bad)


def test_graph_links_source_to_ability():
    g = KB.graph()
    # 플라톤 → 『소피스트』 자료 → 진리 대 설득 → 사고원형 → 반론 이해 (10절 예시 경로)
    assert "person:플라톤" in g["source:SRC-0001"]
    assert "conflict:진리 vs 설득" in g["source:SRC-0001"]
    assert "archetype:ARC-001" in g["conflict:진리 vs 설득"]
    assert "ability:counter" in g["archetype:ARC-001"]
    m = KB.source_map("SRC-0001")
    assert m and m[0]["archetype"].id == "ARC-001" and len(m[0]["topics"]) == 4   # 교차 논제 포함
    assert all(set(a.sources) != set(b.sources) and shared for a, b, shared in KB.cross_candidates())


def test_diagnosis_builds_full_profile():
    d = demo_diagnose(KB, ANS, "B")
    assert set(d.levels) == set(KB.competencies.ids()) and all(1 <= v <= 5 for v in d.levels.values())
    weak = demo_diagnose(KB, {"D1": "모르겠다", "D2": "네", "D3": ""}, "")
    assert sum(weak.levels.values()) < sum(d.levels.values())
    ad = Adaptive(ThinkState())
    ad.apply_diagnosis(d)
    assert ad.overall() in ("초급", "중급", "고급") and ad.ts.profile == d.levels


def _profile(**lv):
    ts = ThinkState(profile={c: 3 for c in KB.competencies.ids()} | lv)
    return Adaptive(ts)


def test_recommendation_prioritizes_weak_ability_over_interest():
    ad = _profile(rebut=1, counter=1, define=4, understand=4)
    ad.ts.interests = ["공정"]                     # 관심은 '공정'(TOP-007: draft 라 제외) — 흥미보다 취약 역량이 먼저
    top = ad.most_needed()
    assert top and {"counter", "rebut"} & set(top.topic.abilities)
    assert any("보완 영역" in r for r in top.reasons)
    assert all(r.topic.review == "approved" for r in ad.recommend(n=10))


def test_difficulty_targets_slightly_above_current_level():
    low = _profile(**{c: 1 for c in KB.competencies.ids()})
    high = _profile(**{c: 5 for c in KB.competencies.ids()})
    assert low.most_needed().topic.level < high.most_needed().topic.level


def _hist(tid, path="recommended"):
    t = KB.topic(tid)
    return HistoryItem(topic=t.id, archetypes=t.archetypes, conflicts=sorted(KB.topic_conflicts(t)),
                       form=t.form, level=t.level, path=path)


def test_repetition_prevention_and_harder_variant():
    ad = _profile(define=2, counter=2)
    ad.ts.history.append(_hist("TOP-G05"))                     # ARC-G03 Level 2 를 했다면
    ids = [t.id for t in ad.eligible()]
    assert "TOP-G05" not in ids and "TOP-G04" in ids           # 같은 사고원형은 더 높은 난이도(Level 4)로만
    ad.ts.history.append(_hist("TOP-G01"))                     # ARC-G01 Level 3 를 했다면
    ids = [t.id for t in ad.eligible()]
    assert "TOP-G02" not in ids                                # 더 쉬운 Level 1 변형은 다시 나오지 않음


def test_three_entry_paths():
    ad = _profile(rebut=2)
    ad.ts.interests = ["자유"]
    ad.ts.history.append(_hist("TOP-G01"))
    rec = ad.recommend("recommended")
    intr = ad.recommend("interest", "정의")
    exp = ad.recommend("explore")
    assert rec and intr and exp
    assert all("정의" in (KB.topic_concepts(r.topic) | KB.topic_fields(r.topic)) or
               any("정의" in KB.archetype(a).question for a in r.topic.archetypes) for r in intr)
    hist_conf = set(ad.ts.history[0].conflicts)
    assert all(not (KB.topic_conflicts(r.topic) & hist_conf) for r in exp)
    assert all("편식" in r.reasons[0] for r in exp)


def test_structure_draft_demo_marks_review():
    d = structure_draft(KB, "시험용 평론", "소피스트는 진리보다 설득을 앞세웠다. 다수의 동의는 진리의 근거가 될 수 있는가? 대중은 쉽게 흔들린다.")
    assert "진리" in d["concepts"] and "진리 vs 설득" in d["conflicts"] and "ARC-001" in d["cross_links"]
    assert d["review"]["status"] == "draft" and "archetypes" in d["review"]["must_review"]


# ---------------------------------------------------------------- 웹
@pytest.fixture()
def client(monkeypatch):
    mem = store_mod.MemoryStore()
    monkeypatch.setattr("web.main.get_store", lambda: mem)
    c = TestClient(app)
    c.mem = mem
    c.post("/login", data={"login_id": "test", "password": "testpoc"})
    return c


def test_web_diagnose_recommend_start(client):
    c = client
    r = c.get("/think", follow_redirects=True)
    assert "지금 내 생각의 모양" in r.text and "입장 A" in r.text
    r = c.post("/think/diagnose", data={"D1": "짧다", "D2": "", "D3": ""}, follow_redirects=True)
    assert "두 과제는" in r.text
    r = c.post("/think/diagnose", data={**ANS, "choice": "B", "interests": ["자유", "진리"]}, follow_redirects=True)
    assert "지금 수준" in r.text and "능력별 프로파일" in r.text and "가장 필요한 학습" in r.text
    r = c.get("/think")
    assert "지금 나에게 가장 필요한 학습" in r.text and "맞춤 추천학습" in r.text
    for path in ("interest", "explore"):
        assert c.get(f"/think?path={path}").status_code == 200
    sid = next(iter(c.mem.states))
    ts = ThinkState.model_validate(c.mem.load(sid).think)
    tid = Adaptive(ts).most_needed().topic.id
    r = c.post(f"/think/start/{tid}", data={"path": "recommended"}, follow_redirects=True)
    assert "처음 생각" in r.text and "생각해 볼 갈림길" in r.text
    c.post(f"/think/topic/{tid}/first", data={"text": "지금 내 생각은 이렇다."})
    ts = ThinkState.model_validate(c.mem.load(sid).think)
    assert ts.history[-1].topic == tid and ts.history[-1].first_thought.startswith("지금")
    assert ts.interests == ["자유", "진리"]
    assert tid not in [r.topic.id for r in Adaptive(ts).recommend(n=10)]     # 시작한 논제는 다시 추천하지 않음
    assert c.post("/think/start/TOP-007", data={"path": "recommended"}, follow_redirects=False).status_code == 303   # 검수 전 논제는 시작 불가
    assert not any(h.topic == "TOP-007" for h in ThinkState.model_validate(c.mem.load(sid).think).history)


def test_web_teacher_knowledge(client):
    c = client
    r = c.get("/teacher/knowledge?src=SRC-0001")
    assert "지식자산 · 사고원형 DB" in r.text and "50편 시범 DB" in r.text and "사고의 지도" in r.text
    assert "다수의 동의는 진리의 근거가 될 수 있는가?" in r.text
    r = c.post("/teacher/knowledge/structure", data={"title": "시험", "text": "소피스트는 진리보다 설득을 앞세웠다. " * 3})
    assert "사고구조 초안" in r.text and "진리 vs 설득" in r.text and "검수" in r.text
    assert "입력 안내" in c.get("/teacher/knowledge/template.yaml").text


def test_pilot_batches_and_catalog():
    """책 5권에서 만든 50편 시범 DB (전문가 검수 완료)와 전체 편 목록."""
    from src.think.kb import catalog
    real = [s for s in KB.sources if s.review.get("status") == "approved"]
    assert len(real) >= 50 and all(s.public != "full" for s in real)
    assert sum(p["done"] for p in KB.pilot_progress()) >= 50
    books = catalog()
    assert len(books) >= 7 and sum(b["count"] for b in books) >= 520      # 고전평론 185편(198개 원고)·『지혜 사용설명서』 포함
    from src.think.kb import inventory
    inv = inventory()
    assert inv["unique"] == inv["total"] - inv["duplicates"] and inv["duplicates"] > 0   # 같은 고전 평론은 한 번만
    assert sum(1 for b in books if b["structured"] >= 5) == 5               # 시범 구조화는 5권에서
    real_topics = [t for t in KB.approved_topics() if t.id.startswith(("TOP-J", "TOP-H", "TOP-G", "TOP-C", "TOP-K"))]
    assert len(real_topics) >= 70


def test_real_data_recommendation_uses_reviewed_assets():
    """리얼 데이터 시험: 검수된 원천 저작 기반 논제가 추천되고, 학생 화면에 자료 제목·저자는 나오지 않는다."""
    ad = Adaptive(ThinkState())
    ad.apply_diagnosis(demo_diagnose(KB, ANS, "B"))
    recs = ad.recommend(n=5)
    assert any(r.topic.id.startswith(("TOP-J", "TOP-H", "TOP-G", "TOP-C", "TOP-K")) for r in recs)
