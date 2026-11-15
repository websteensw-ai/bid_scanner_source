"""AI 다섯 역할 (가이드 5장): 문답 튜터 · 단계 판정자 · 채점자 · 첨삭 생성기 · 응답 검사기(guardrail.py).

역할마다 데모 구현(규칙 기반, API 키 없이 동작)과 LLM 구현이 같은 인터페이스를 따른다.
엔진이 진행을 소유하고, AI 는 발화와 구조화 판단만 돌려준다.
"""
import json
import re

from src.learning.intent import _ANSWER_REQUEST, _LAUGH_OR_MASH, _OFF_TASK_PHRASE
from src.mvp.models import EvalItem, StageRun, TutorJudgment
from src.mvp.pack import ISSUE_TYPES, Pack, Rubric, StageCard, StageCards
from src.mvp.text import official_count, sentences

TUTOR_PROMPT = "tutor-0.1"
JUDGE_PROMPT = "judge-0.1"
GRADER_PROMPT = "grader-0.1"
FEEDBACK_PROMPT = "feedback-0.1"
THREAD_PROMPT = "thread-0.1"

DANGER_TEXT = ("지금 많이 힘든 마음이 느껴져요. 학습은 잠시 멈출게요. 혼자 견디지 말고 담임·상담 선생님께 "
               "이야기해 주세요. 지금 바로 도움이 필요하면 청소년상담 1388(전화·문자) 또는 자살예방상담 109로 "
               "연락할 수 있어요. 선생님께도 알림을 보냈어요.")
_DANGER = re.compile(r"(죽고\s*싶|자살|자해|죽어\s*버리|사라지고\s*싶|살기\s*싫|목숨)")
_DONT_KNOW = re.compile(r"(모르겠|모르겟|잘\s*모르|몰라요|모름|감이\s*안)")
_DISAGREE = re.compile(r"(동의하지\s*않|아닌\s*것\s*같|틀린\s*것\s*같|제\s*생각은\s*달라|그렇지\s*않|잘못\s*짚)")
_REF = re.compile(r"[가나다]\s*-\s*\d")

CHARTER = """너는 고등학생의 논술 학습을 돕는 소크라틱 문답 튜터다. (엘렝코스: 질문으로 생각의 빈틈을 스스로 찾게 한다)
필수 원칙
- 학생의 말에서 출발하고, 학생이 원문(문단 번호)에서 근거를 찾게 한다.
- 한 발화에 질문은 하나만, 250자 이내로 말한다.
- 모범답안·기준 해석 문장을 먼저 말하지 않는다. 학생 대신 완성 문장을 쓰지 않는다.
- 보충 사다리는 한 턴에 한 칸만 오른다. 이미 충족한 하위 목표는 다시 묻지 않는다.
- 학생이 타당하게 반대하면 지적을 거두고, 그 사실을 판단에 남긴다.
- 과제와 무관한 말에는 한 문장으로 답하고 현재 질문으로 돌아온다.
- 제시문 밖 배경지식은 원문으로 돌려보낸다.
말투: ‘~요/~세요’체. 지원 수준은 학생에게 말하지 않는다.
출력: 아래 JSON 하나만.
{"utterance": "...", "subgoal_id": "...", "subgoal_status": "met|partial|not_yet", "issue_type": null 또는
 ["keyword_only","case_as_claim","overclaim","background_knowledge","false_identity","false_dichotomy","not_linked_to_task"] 중 하나,
 "student_quote": "...", "passage_refs": ["가-1"], "scaffold_level": 0~5, "support_level_so_far": "independent|question_then_revised|scaffolded|explained_then_restated",
 "thinking_change": null 또는 {"before": "...", "after": "...", "note": "..."}, "handoff_note": "...", "flag_teacher": false}"""


def _has(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def _groups_met(text: str, groups: list[list[str]]) -> bool:
    return bool(groups) and all(_has(text, g) for g in groups)


def _quote(text: str, n: int = 24) -> str:
    t = re.sub(r"\s+", " ", text.strip())
    return t if len(t) <= n else t[:n] + "…"


# ====================================================================== 튜터
class TutorContext:
    def __init__(self, cards: StageCards, card: StageCard, pack: Pack, run: StageRun, text: str,
                 prior_outputs: dict[str, dict[str, str]]):
        self.cards, self.card, self.pack, self.run, self.text = cards, card, pack, run, text
        self.prior_outputs = prior_outputs
        sg = card.subgoals[run.subgoal_idx] if run.subgoal_idx < len(card.subgoals) else None
        self.subgoal = sg
        self.view = pack.view_tutor(card.id, sg.id if sg else None)


class Tutor:
    name = "demo"
    model = "rules"

    def respond(self, ctx: TutorContext, feedback: str = "") -> tuple[str, TutorJudgment]:
        raise NotImplementedError


class DemoTutor(Tutor):
    """규칙 기반 튜터. 패키지의 demo_signals 와 단계 카드의 사다리로 움직인다."""

    def respond(self, ctx, feedback=""):
        run, card, text, sg = ctx.run, ctx.card, ctx.text.strip(), ctx.subgoal
        refs = sorted({re.sub(r"\s", "", m) for m in _REF.findall(text)})
        j = TutorJudgment(subgoal_id=sg.id if sg else None, student_quote=_quote(text, 60), passage_refs=refs,
                          scaffold_level=run.rung)
        if _DANGER.search(text):
            j.intent, j.flag_teacher = "danger", True
            j.handoff_note = "위험 신호 — 학습 중단, 교사 알림"
            return DANGER_TEXT, j
        ov = ctx.pack.stage_overrides.get(sg.id) if sg else None
        q0 = (ov.first_question if ov and ov.first_question else card.central_question)

        if _ANSWER_REQUEST.search(text):
            j.intent = "answer_request"
            j.scaffold_level = 5 if run.answer_requests >= 1 else min(run.rung + 1, 5)
            return "답을 바로 알려 드리면 내 실력이 되지 않아요. 대신 " + self._rung_text(ctx, j.scaffold_level, q0), j
        if _LAUGH_OR_MASH.match(text) or (_OFF_TASK_PHRASE.search(text) and len(text) <= 40):
            j.intent = "off_task"
            return f"잠깐 쉬어 가도 괜찮아요. 다시 돌아와서, {q0}", j
        if _DONT_KNOW.search(text) and len(text) <= 30:
            j.intent = "dont_know"
            j.scaffold_level = min(run.rung + 1, 5)
            return "괜찮아요, 더 작게 나눠 볼게요. " + self._rung_text(ctx, j.scaffold_level, q0), j

        errs = [e for e in ctx.view["error_patterns"] if _has(text, e.demo_signals)]
        if _DISAGREE.search(text):
            j.intent = "disagree"
            if refs:
                j.handoff_note = "학생의 타당한 반대 — AI 지적 철회 (AI 오류로 기록)"
                j.subgoal_status = "met" if ov and _groups_met(text, ov.demo_signals) else "partial"
                if j.subgoal_status == "met":
                    return self._advance(ctx, j, prefix="말해 준 근거가 타당해요. 제가 앞에서 잘못 짚었어요. "), j
                return f"{', '.join(refs)}를 근거로 든 점이 타당해요. 제 지적은 거둘게요. 그 근거로 보면 {q0}", j
            return "그렇게 생각한 근거가 되는 문단을 하나 짚어 줄 수 있나요?", j

        if ov and _groups_met(text, ov.demo_signals) and not errs:
            j.subgoal_status = "met"
            flagged = next((i for i in range(len(run.turns) - 1, -1, -1)
                            if run.turns[i].role == "tutor" and run.turns[i].judgment
                            and run.turns[i].judgment.subgoal_id == sg.id and run.turns[i].judgment.issue_type), None)
            if flagged is not None and flagged > 0 and run.turns[flagged - 1].role == "student":
                j.thinking_change = {"before": _quote(run.turns[flagged - 1].text, 80), "after": _quote(text, 80),
                                     "note": f"{sg.id}: {run.turns[flagged].judgment.issue_type} 지적 후 재진술"}
            return self._advance(ctx, j), j

        if errs:
            e = errs[0]
            j.issue_type, j.error_code, j.subgoal_status = e.issue_type, e.code, "partial"
            repeated = any(t.judgment and t.judgment.error_code == e.code for t in run.turns if t.role == "tutor")
            j.scaffold_level = min(run.rung + 1, 5) if repeated else run.rung
            if repeated:
                return self._rung_text(ctx, j.scaffold_level, e.first_question), j
            return f"‘{_quote(text)}’라고 했어요. {e.first_question}", j

        j.subgoal_status = "partial" if ov and any(_has(text, g) for g in ov.demo_signals) else "not_yet"
        rec = run.subgoals.get(sg.id) if sg else None
        if j.subgoal_status == "partial" and len(text) < 12:
            j.issue_type = "keyword_only"
            return f"‘{_quote(text)}’가 원문에서 어떤 뜻으로 쓰였는지 한 문장으로 말해 볼까요?", j
        stalled = rec is not None and rec.turns >= 1 and rec.turns % 2 == 1
        j.scaffold_level = min(run.rung + 1, 5) if stalled else run.rung
        return self._rung_text(ctx, j.scaffold_level, q0, text), j

    # ---- 사다리 발화
    def _rung_text(self, ctx: TutorContext, rung: int, q0: str, text: str = "") -> str:
        sg = ctx.subgoal
        ov = ctx.pack.stage_overrides.get(sg.id) if sg else None
        refs = re.findall(r"[가나다]-\d", ov.criterion if ov else "")
        ref = refs[0] if refs else next((p.id for ps in ctx.pack.exam.passages for p in ps.paragraphs), "")
        concept = next((c for c in ctx.view["key_concepts"]), None)
        if rung <= 0:
            return q0
        if rung == 1:
            if text:
                return f"‘{_quote(text)}’라고 했는데, 그렇게 생각한 까닭을 한 문장으로 더 말해 볼까요?"
            return f"{ref} 문단에 실마리가 있어요. 그 문단을 읽고 떠오르는 낱말 하나만 말해 볼까요?"
        if rung == 2:
            return f"{ref} 문단을 다시 읽고, 그 문단이 이 질문과 어떻게 이어지는지 말해 볼까요?"
        if rung == 3:
            return f"‘{sg.goal if sg else q0}’을 생각할 때, 원문이 직접 말한 것과 말하지 않은 것 가운데 어느 쪽부터 찾아볼까요?"
        if rung == 4 and concept:
            return f"도움말: ‘{concept['term']}’은 이 글에서 ‘{concept['meaning']}’이라는 뜻이에요. 이 뜻을 넣어 내 말로 다시 말해 볼까요?"
        return f"예를 들어 ‘{ref}에 따르면 …’처럼 시작해 볼 수 있어요. 이어서 내 문장으로 완성해 볼까요?"

    def _advance(self, ctx: TutorContext, j: TutorJudgment, prefix: str = "") -> str:
        card, run = ctx.card, ctx.run
        done = {k for k, v in run.subgoals.items() if v.status in ("met", "skipped")} | {j.subgoal_id}
        nxt = next((s for s in card.subgoals if s.id not in done), None)
        quote = f"‘{_quote(ctx.text)}’ — 원문에 기대어 잘 말했어요. " if not prefix else prefix
        if nxt is None:
            return quote + "이 단계에서 할 일을 모두 했어요. 이제 ‘단계 정리’에서 내 말로 정리해 볼까요?"
        ov = ctx.pack.stage_overrides.get(nxt.id)
        return quote + (ov.first_question if ov and ov.first_question else nxt.goal)


class LLMTutor(Tutor):
    def __init__(self, provider):
        self.provider = provider
        self.name, self.model = provider.name, provider.model

    def respond(self, ctx, feedback=""):
        card, v = ctx.card, ctx.view
        system = (CHARTER + "\n\n<단계_카드>\n" + json.dumps(
            {"stage": card.id, "name": card.name, "central_question": card.central_question, "scope": card.scope,
             "subgoals": [s.model_dump() for s in card.subgoals],
             "ladder": [r.model_dump() for r in ctx.cards.ladder], "forbidden": ctx.cards.forbidden},
            ensure_ascii=False) + "\n</단계_카드>")
        exemplars = [x.model_dump() for x in v["exemplars"]]
        user = json.dumps({
            "시험지": v["exam"].model_dump(),
            "필수_수행(튜터_참조)": v["required_tasks"], "제시문_역할": v["passage_roles"],
            "이_단계_핵심_개념": v["key_concepts"], "설명_기준(튜터_참조, 학생에게_말하지_말_것)": v["explanation_criteria"],
            "이_단계_오류_우선질문": [e.model_dump(exclude={"demo_signals"}) for e in v["error_patterns"]],
            "하위목표_완료기준": {k: o.criterion for k, o in v["overrides"].items()},
            "예시_장면(말투와_질문_수준만_참고, 내용_재현_금지)": exemplars,
            "이전_단계_산출물": ctx.prior_outputs,
            "현재_하위목표": ctx.subgoal.model_dump() if ctx.subgoal else None,
            "하위목표_상태": {k: r.status for k, r in ctx.run.subgoals.items()},
            "보충_사다리_위치": ctx.run.rung,
            "이번_단계_대화": [{"role": t.role, "text": t.text} for t in ctx.run.turns[-30:]],
            "학생_발화": ctx.text,
        }, ensure_ascii=False)
        if feedback:
            user += f"\n\n[검사기] 앞 발화가 불합격했다: {feedback}. 규칙을 지켜 다시 써라."
        raw = self.provider._complete(system, user)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise ValueError("튜터 응답 형식 오류")
        d = json.loads(m.group(0))
        utter = str(d.pop("utterance", "")).strip()
        if d.get("issue_type") not in ISSUE_TYPES:
            d["issue_type"] = None
        j = TutorJudgment.model_validate({k: v for k, v in d.items() if k in TutorJudgment.model_fields})
        return utter, j


# ====================================================================== 단계 판정자
class Judge:
    def judge(self, card: StageCard, pack: Pack, fields: dict[str, str]) -> tuple[bool, str, str | None]:
        """(통과, 메모, 다시 물을 칸 key)."""
        raise NotImplementedError


class DemoJudge(Judge):
    def judge(self, card, pack, fields):
        for f in card.outputs:
            if len(fields.get(f.key, "").strip()) < f.min_chars:
                return False, f"‘{f.label}’ 칸을 조금 더 채워 주세요.", f.key
        allt = " ".join(fields.values())
        missed = [sg for sg in card.subgoals
                  if not any(_has(allt, g) for g in pack.stage_overrides[sg.id].demo_signals)]
        if len(missed) > len(card.subgoals) // 2:
            return False, f"‘{missed[0].goal}’이 정리에 드러나지 않아요.", card.outputs[0].key
        return True, "완료 기준 충족", None


class LLMJudge(Judge):
    def __init__(self, provider):
        self.provider = provider

    def judge(self, card, pack, fields):
        system = ("너는 논술 학습의 단계 판정자다. 학생이 쓴 단계 정리가 하위 목표의 완료 기준을 충족하는지 본다. "
                  'JSON 하나만: {"pass": true|false, "note": "학생에게 보일 한 문장(~요체)", "field": "다시 물을 칸 key 또는 null"}')
        user = json.dumps({"stage": card.model_dump(include={"id", "name", "subgoals", "outputs"}),
                           "criteria": {sg.id: pack.stage_overrides[sg.id].criterion for sg in card.subgoals},
                           "fields": fields}, ensure_ascii=False)
        m = re.search(r"\{.*\}", self.provider._complete(system, user), re.DOTALL)
        d = json.loads(m.group(0)) if m else {"pass": False, "note": "판정 응답 형식 오류", "field": None}
        return bool(d.get("pass")), str(d.get("note", "")), d.get("field")


# ====================================================================== 채점자
class Grader:
    name = "demo-grader"

    def grade(self, pack: Pack, rubric: Rubric, body: str) -> list[EvalItem]:
        raise NotImplementedError


def _first_sentence_with(body: str, words: list[str]) -> dict | None:
    for s in sentences(body):
        if _has(s, words):
            i = body.find(s)
            return {"start": i, "end": i + len(s), "quote": s}
    return None


class DemoGrader(Grader):
    def grade(self, pack, rubric, body):
        out = []
        chars = official_count(body)
        sents = sentences(body)
        for ri in rubric.items:
            ev, err = [], None
            if not body.strip():
                out.append(EvalItem(code=ri.code, level=0, reason="답안 없음", confidence="high"))
                continue
            if ri.code == "E1":
                avg = sum(len(s) for s in sents) / max(len(sents), 1)
                level = 4 if avg <= 60 else 3 if avg <= 80 else 2
                long_s = max(sents, key=len) if sents else ""
                if long_s and len(long_s) > 80:
                    i = body.find(long_s)
                    ev = [{"start": i, "end": i + len(long_s), "quote": long_s}]
                reason = f"문장 평균 {avg:.0f}자"
            elif ri.code == "E2":
                level = 4 if chars >= pack.max_chars * 0.6 else 2
                reason = f"본문 {chars}자 / {pack.max_chars}자"
            else:
                groups = ri.demo_signals
                hit = sum(1 for g in groups if _has(body, g))
                level = 4 if not groups else round(4 * hit / len(groups))
                reason = f"{ri.name}: 신호 {hit}/{len(groups)}" if groups else ri.name
                for g in groups:
                    if (e := _first_sentence_with(body, g)):
                        ev = [e]
                        break
                neg = [w for w in ri.demo_negative if w in body]
                if neg:
                    level = min(level, 1 if ri.code != "A2" else 2)
                    ev = [e] if (e := _first_sentence_with(body, neg)) else ev
                    reason = f"{ri.name}: ‘{neg[0]}’ 표현"
                    err = {"B3": "trust_equals_truth", "D2": "outer_only_inner_only"}.get(ri.code)
            out.append(EvalItem(code=ri.code, level=level, evidence=ev, reason=reason, error_code=err))
        return out


class LLMGrader(Grader):
    def __init__(self, provider):
        self.provider = provider
        self.name = f"{provider.name}:{provider.model}"

    def grade(self, pack, rubric, body):
        system = ("너는 논술 채점자다. 학생과 대화하지 않는다. 채점표 항목마다 수준(0~4)과 근거 구절을 낸다. "
                  "점수는 계산하지 마라(코드가 계산한다). 근거 구절은 답안에서 그대로 복사하고 문자 위치(start, end)를 적는다. "
                  "판단할 수 없으면 level 을 null 로 둔다. 예시답안은 유일한 정답이 아니다. "
                  "중복 감점 방지 규칙을 지킨다.\n"
                  'JSON 하나만: {"items":[{"code":"B3","level":2,"evidence":[{"start":0,"end":10,"quote":"..."}],'
                  '"reason":"...","error_code":null,"confidence":"low|medium|high"}]}')
        user = json.dumps({"grader_view": {k: (v.model_dump() if hasattr(v, "model_dump") else
                                               [x.model_dump() if hasattr(x, "model_dump") else x for x in v]
                                               if isinstance(v, list) else v)
                                           for k, v in pack.view_grader().items()},
                           "rubric": rubric.model_dump(exclude={"items": {"__all__": {"demo_signals", "demo_negative"}}}),
                           "answer": body}, ensure_ascii=False)
        m = re.search(r"\{.*\}", self.provider._complete(system, user), re.DOTALL)
        items = json.loads(m.group(0)).get("items", []) if m else []
        known = {i.code for i in rubric.items}
        got = {it["code"]: EvalItem.model_validate(it) for it in items if it.get("code") in known}
        return [got.get(c) or EvalItem(code=c, level=None, reason="판정 보류") for c in [i.code for i in rubric.items]]


# ====================================================================== 6-1 문답 (첨삭 스레드)
THREAD_QUESTIONS = [
    "{n}로 표시한 ‘{q}’에서 하려던 말을 내 말로 다시 설명해 볼까요?",
    "그 설명을 뒷받침하는 제시문 문단은 어디인가요?",
    "이 구절은 논제의 세 요구 가운데 무엇을 하는 부분인가요?",
    "‘{m}’ — 이 질문을 떠올리면, 이 구절을 고칠까요, 그대로 둘까요? 아래에서 판단을 골라 주세요.",
    "고친 문장이 처음 하려던 말을 그대로 살리고 있는지 한 번 더 읽어 볼까요?",
]


def thread_question(step: int, number: str, quote: str, margin: str) -> str:
    step = max(0, min(step, len(THREAD_QUESTIONS) - 1))
    return THREAD_QUESTIONS[step].format(n=number, q=_quote(quote or "이 부분", 30), m=margin)


def thread_stalled(text: str) -> bool:
    return bool(_DONT_KNOW.search(text)) or len(text.strip()) < 4


# ====================================================================== 공장
def _provider_or_none(demo: bool):
    from src.ai.factory import get_provider
    from src.core.config import get_settings

    s = get_settings()
    key = s.anthropic_api_key if s.ai_provider == "claude" else s.openai_api_key
    return get_provider(s) if key else None


def get_roles(demo: bool) -> dict:
    p = _provider_or_none(demo)
    if p is None:
        return {"tutor": DemoTutor(), "judge": DemoJudge(), "grader": DemoGrader(), "provider": None}
    return {"tutor": LLMTutor(p), "judge": LLMJudge(p), "grader": LLMGrader(p), "provider": p}
