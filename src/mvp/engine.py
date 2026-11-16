"""6단계 논술학습 엔진 (가이드 3·4·7·8·9장).

엔진이 진행을 소유한다: 단계 상태(locked→in_progress→summarizing→judging→completed / flagged),
하위 목표, 보충 사다리, 턴 한도, 단계 정리, 원고 버전 고정, 채점 계산, 첨삭 표시와 학생 판단.
AI 는 발화와 구조화 판단만 내고, 엔진이 그 판단을 규칙에 맞게 반영한다.
"""
import difflib
import re
import secrets

from src.learning.state import LearnerState, now
from src.mvp import ai as roles_mod
from src.mvp.guardrail import FALLBACK, light_check, rule_check
from src.mvp.models import (
    Alert,
    Annotation,
    Appeal,
    Audit,
    DraftVersion,
    EvalItem,
    Evaluation,
    MvpAttempt,
    OutputValue,
    Reflection,
    SelfCheck,
    SelfCheckEntry,
    StageOutput,
    StageRun,
    SubgoalRecord,
    ThinkingChange,
    ThreadTurn,
    Turn,
    TutorJudgment,
    WritingEvent,
)
from src.mvp.pack import SUPPORT_LEVELS, load_problem, reflection_items, stage_cards
from src.mvp.scoring import compute, fix_evidence, merge_runs
from src.mvp.text import MAX_CELLS, cells_used, containment, official_count, sentences

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
_FUNCTION_Q = re.compile(r"(글자\s*수|원고지|제출|저장|칸|분량|조건|버튼|시간|줄바꿈|문단|띄어)")
FUNCTION_ANSWERS = [
    (re.compile(r"글자\s*수|분량"), "공식 글자 수는 입력한 본문의 글자 수예요(공백·문장부호 포함, 줄바꿈 제외). 700자를 넘으면 분량 항목이 0점이 돼요."),
    (re.compile(r"원고지|칸|띄어|줄바꿈|문단"), "Enter 를 누르면 새 문단이 되고, 원고지 미리보기는 자동으로 첫 칸을 비워요. 자세한 규칙은 ‘원고지 작성법’을 보세요."),
    (re.compile(r"제출|저장"), "글은 10초마다 임시 저장돼요. ‘초고 완성’ → 자기검증 → ‘제출’ 순서로 진행해요. 제출하면 고칠 수 없어요."),
]


class MvpError(Exception):
    pass


def circled(n: int) -> str:
    return CIRCLED[n - 1] if 0 < n <= len(CIRCLED) else f"({n})"


class MvpEngine:
    def __init__(self, state: LearnerState, roles: dict | None = None, attempt_id: str | None = None):
        self.state = state
        self.roles = roles or roles_mod.get_roles(demo=True)
        self.cards = stage_cards()
        aid = attempt_id or self.latest_id()
        self.attempt: MvpAttempt | None = MvpAttempt.model_validate(state.mvp[aid]) if aid else None
        if self.attempt:
            self.pack, self.rubric = load_problem(self.attempt.pack_id)

    # ------------------------------------------------------------------ 회차
    def latest_id(self) -> str | None:
        if not self.state.mvp:
            return None
        return max(self.state.mvp, key=lambda k: self.state.mvp[k].get("started_at", ""))

    def start(self, pack_id: str = "BASIC-Q1") -> MvpAttempt:
        pack, rubric = load_problem(pack_id)
        a = MvpAttempt(id=f"att-{secrets.token_hex(4)}", pack_id=pack.id, pack_version=pack.version,
                       rubric_version=rubric.full_id, cards_version=self.cards.version,
                       onboarded=any(x.get("onboarded") for x in self.state.mvp.values()))
        for sid in self.cards.order():
            card = self.cards.get(sid)
            a.stages[sid] = StageRun(stage=sid, subgoals={sg.id: SubgoalRecord() for sg in card.subgoals})
        a.stages["0"].status = "in_progress"
        a.stages["0"].started_at = now()
        self.attempt, self.pack, self.rubric = a, pack, rubric
        self.save()
        return a

    def save(self) -> None:
        if self.attempt:
            self.state.mvp[self.attempt.id] = self.attempt.model_dump(mode="json")

    def need(self) -> MvpAttempt:
        if not self.attempt:
            raise MvpError("진행 중인 회차가 없어요.")
        return self.attempt

    def run(self, sid: str | None = None) -> StageRun:
        a = self.need()
        return a.stages[sid or a.current]

    def audit(self, who: str, action: str, target: str = "") -> None:
        self.need().audit.append(Audit(who=who, action=action, target=target))

    def alert(self, kind: str, stage: str, detail: str) -> None:
        a = self.need()
        if any(x.kind == kind and x.stage == stage and x.status != "done" and x.detail == detail for x in a.alerts):
            return
        a.alerts.append(Alert(kind=kind, stage=stage, detail=detail))

    def prior_outputs(self, upto: str) -> dict[str, dict[str, str]]:
        a = self.need()
        out = {}
        for sid in self.cards.order():
            if sid == upto:
                break
            r = a.stages[sid]
            if r.outputs and r.outputs[-1].verdict == "pass":
                out[f"{sid} {self.cards.get(sid).name}"] = {k: v.value for k, v in r.outputs[-1].fields.items()}
        return out

    def recap(self, idle_minutes: int = 20) -> str:
        """이어하기 요약. 마지막 활동 뒤 idle_minutes 이상 지났을 때만 (대화 중에는 보이지 않음)."""
        from datetime import UTC, datetime, timedelta

        r = self.run()
        card = self.cards.get(r.stage)
        last = r.turns[-1].ts if r.turns else None
        if not last or datetime.now(UTC) - datetime.fromisoformat(last) < timedelta(minutes=idle_minutes):
            return ""
        met = [sg.goal for sg in card.subgoals if r.subgoals[sg.id].status in ("met", "skipped")]
        cur = card.subgoals[r.subgoal_idx].goal if r.subgoal_idx < len(card.subgoals) else "단계 정리"
        done = f"‘{met[-1]}’까지 했어요. " if met else ""
        return f"지난번에는 {card.name} 단계에서 {done}지금 할 일: {cur}"

    # ------------------------------------------------------------------ 1~5단계 문답
    def references(self, stage: str) -> list[str]:
        """튜터 발화와 겹치면 안 되는 문장 (예시답안·설명 기준·완료 기준)."""
        refs = [m.text for m in self.pack.model_answers] + list(self.pack.explanation_criteria.values())
        refs += [o.criterion for k, o in self.pack.stage_overrides.items() if k.startswith(f"S{stage}-")]
        return refs

    def student_turn(self, text: str) -> Turn:
        a, r = self.need(), self.run()
        card = self.cards.get(r.stage)
        text = text.strip()
        if card.kind != "dialogue":
            raise MvpError("이 단계에는 문답창이 없어요.")
        if r.status == "flagged":
            raise MvpError("선생님 확인을 기다리고 있어요. 확인 후 이어서 할 수 있어요.")
        if r.status not in ("in_progress", "summarizing"):
            raise MvpError("지금은 문답을 할 수 없어요.")
        if not text:
            raise MvpError("답을 입력해 주세요.")
        r.turns.append(Turn(role="student", text=text[:2000]))
        r.last_seen = now()
        lim = self.cards.limits
        all_met = all(v.status in ("met", "skipped") for v in r.subgoals.values())
        if all_met:
            r.status = "summarizing"
            t = Turn(role="tutor", text="좋아요. 방금 말한 내용을 ‘단계 정리’에 반영해 볼까요?",
                     judgment=TutorJudgment(intent="answer", subgoal_status="met"), prompt_version="engine")
            r.turns.append(t)
            return t
        sg = card.subgoals[r.subgoal_idx]
        rec = r.subgoals[sg.id]
        rec.turns += 1
        ctx = roles_mod.TutorContext(self.cards, card, self.pack, r, text, self.prior_outputs(r.stage))
        tutor = self.roles["tutor"]
        utter, j, check, regen, rejected = self._generate(tutor, ctx, r.stage)
        # ---- 사다리: 한 턴에 한 칸 (두 번째 정답 요구는 5칸까지 허용 — 5-6)
        cap = 5 if (j.intent == "answer_request" and r.answer_requests >= 1) else r.rung + 1
        if rec.turns % lim["turns_per_subgoal"] == 0:
            j.scaffold_level = max(j.scaffold_level, r.rung + 1)
        r.rung = max(r.rung, min(j.scaffold_level, cap, 5))
        j.scaffold_level = r.rung
        if j.intent == "answer_request":
            r.answer_requests += 1
        sup = self.cards.support_for(r.rung)
        if SUPPORT_LEVELS.index(sup) > SUPPORT_LEVELS.index(r.support):
            r.support = sup
        j.support_level_so_far = r.support
        idx = len(r.turns)
        if j.flag_teacher or j.intent == "danger":
            r.status = "flagged"
            self.alert("danger", r.stage, f"위험 신호: {text[:80]}")
        elif j.subgoal_status == "met" and j.subgoal_id == sg.id:
            rec.status, rec.support, rec.evidence_turn = "met", sup, idx - 1
            self._next_subgoal(r, card)
        elif j.subgoal_status in ("partial", "not_yet"):
            rec.status = j.subgoal_status
        if j.thinking_change:
            a.thinking.append(ThinkingChange(stage=r.stage, before=j.thinking_change.get("before", ""),
                                             after=j.thinking_change.get("after", ""),
                                             note=j.thinking_change.get("note", ""), turn_index=idx - 1))
        if r.student_turns() > lim["turns_per_stage"] and r.status != "completed":
            r.status = "flagged"
            self.alert("stall", r.stage, f"학생 발화 {r.student_turns()}회 초과")
        elif r.rung >= 5 and rec.status != "met" and rec.turns >= 3:
            self.alert("stall", r.stage, f"{sg.id} 사다리 5칸 도달 후 미충족")
        t = Turn(role="tutor", text=utter, judgment=j, prompt_version=roles_mod.TUTOR_PROMPT,
                 model=f"{tutor.name}:{tutor.model}", check=check, regenerated=regen, rejected_drafts=rejected)
        r.turns.append(t)
        return t

    def _generate(self, tutor, ctx, stage: str):
        refs = self.references(stage)
        rejected, feedback = [], ""
        utter, j = "", TutorJudgment()
        for attempt in range(2):                      # 위반 시 한 번 다시 생성
            try:
                utter, j = tutor.respond(ctx, feedback)
            except Exception as e:                    # AI 오류 → 안전한 기본 발화
                return FALLBACK, TutorJudgment(subgoal_id=ctx.subgoal.id if ctx.subgoal else None,
                                               handoff_note=f"튜터 오류: {e}"), {"ok": False, "reasons": ["error"]}, attempt, rejected
            if j.intent == "danger":
                return utter, j, {"ok": True, "reasons": [], "fixed_text": True}, attempt, rejected
            check = rule_check(utter, refs, self.cards.limits["max_utterance_chars"])
            light = light_check(self.roles.get("provider"), utter) if check["ok"] else None
            if light is False:
                check = {**check, "ok": False, "reasons": check["reasons"] + ["해석 대신 제시"]}
            check["light"] = light
            if check["ok"]:
                return utter, j, check, attempt, rejected
            rejected.append(utter)
            feedback = ", ".join(check["reasons"])
        return FALLBACK, j, {**check, "fallback": True}, 1, rejected

    def _next_subgoal(self, r: StageRun, card) -> None:
        r.rung = 0
        nxt = next((i for i, s in enumerate(card.subgoals) if r.subgoals[s.id].status not in ("met", "skipped")), None)
        if nxt is None:
            r.subgoal_idx = len(card.subgoals)
            r.status = "summarizing"
        else:
            r.subgoal_idx = nxt

    def skip_subgoal(self) -> None:
        r = self.run()
        card = self.cards.get(r.stage)
        if r.subgoal_idx >= len(card.subgoals) or r.status != "in_progress":
            raise MvpError("건너뛸 하위 목표가 없어요.")
        sg = card.subgoals[r.subgoal_idx]
        r.subgoals[sg.id].status = "skipped"
        r.turns.append(Turn(role="system", text=f"‘{sg.goal}’을 건너뛰었어요. 단계 정리에서 다시 확인해요."))
        self._next_subgoal(r, card)

    # ------------------------------------------------------------------ 단계 정리 (4장)
    def summary_candidates(self) -> dict[str, tuple[str, int | None]]:
        """칸마다 학생이 대화 중 직접 한 말을 후보로. AI 발화는 후보가 될 수 없다."""
        r = self.run()
        card = self.cards.get(r.stage)
        student = [(i, t.text) for i, t in enumerate(r.turns) if t.role == "student"]
        out = {}
        for k, f in enumerate(card.outputs):
            sg = card.subgoals[k] if k < len(card.subgoals) else None
            idx = r.subgoals[sg.id].evidence_turn if sg else None
            if idx is not None and r.turns[idx].role == "student":
                out[f.key] = (r.turns[idx].text, idx)
            elif student:
                out[f.key] = (student[-1][1], student[-1][0]) if k == len(card.outputs) - 1 else ("", None)
            else:
                out[f.key] = ("", None)
        if r.outputs:                                  # 다시 정리할 때는 직전 정리에서 시작
            last = r.outputs[-1].fields
            out = {k: (last[k].value, last[k].turn_index) if k in last else v for k, v in out.items()}
        return out

    def submit_summary(self, fields: dict[str, str]) -> StageOutput:
        r = self.run()
        card = self.cards.get(r.stage)
        if r.status not in ("summarizing", "in_progress"):
            raise MvpError("지금은 단계 정리를 할 수 없어요.")
        if r.status == "in_progress" and not all(v.status in ("met", "skipped") for v in r.subgoals.values()):
            raise MvpError("하위 목표를 마친 뒤에 정리할 수 있어요.")
        student = {t.text.strip(): i for i, t in enumerate(r.turns) if t.role == "student"}
        vals = {}
        for f in card.outputs:
            v = fields.get(f.key, "").strip()[:1000]
            i = student.get(v)
            vals[f.key] = OutputValue(value=v, source="student_turn" if i is not None else "typed", turn_index=i)
        out = StageOutput(version=len(r.outputs) + 1, fields=vals)
        r.outputs.append(out)
        r.status = "judging"
        ok, note, field = self.roles["judge"].judge(card, self.pack, {k: v.value for k, v in vals.items()})
        out.verdict, out.verdict_note = ("pass" if ok else "fail"), note
        if ok:
            self._complete_stage(r)
        else:
            r.status = "in_progress"
            label = next((f.label for f in card.outputs if f.key == field), "정리")
            r.turns.append(Turn(role="tutor", text=f"정리에서 ‘{label}’ 칸을 다시 볼게요. {note}"[:250],
                                prompt_version=roles_mod.JUDGE_PROMPT))
        return out

    def _complete_stage(self, r: StageRun) -> None:
        a = self.need()
        r.status, r.finished_at = "completed", now()
        order = self.cards.order()
        if a.diagnosis.get("supplementing") == r.stage:          # 6단계 중단 후 보충 → 6단계로 복귀
            a.diagnosis.pop("supplementing")
            a.current = "6"
            return
        nxt = order[order.index(r.stage) + 1] if order.index(r.stage) + 1 < len(order) else None
        if nxt:
            a.current = nxt
            n = a.stages[nxt]
            if n.status == "locked":
                n.status, n.started_at = "in_progress", now()

    # ------------------------------------------------------------------ 6단계 독립 작성 (7장)
    def _ensure_stage(self, sid: str) -> StageRun:
        a = self.need()
        if a.current != sid:
            raise MvpError("지금 단계가 아니에요.")
        return a.stages[sid]

    def autosave(self, body: str, paste_sizes: list[int] | None = None, accessibility: bool = False) -> dict:
        a = self.need()
        r = self._ensure_stage("6")
        if a.draft("submitted"):
            raise MvpError("제출본은 고칠 수 없어요.")
        body = body.replace("\r", "")
        cells = cells_used(body)
        if cells > MAX_CELLS:
            raise MvpError(f"원고지 {MAX_CELLS}칸을 넘었어요. ({cells}칸)")
        if not a.writing_started:
            a.writing_started = now()
            a.events.append(WritingEvent(kind="start"))
            r.started_at = r.started_at or now()
        for size in paste_sizes or []:
            a.events.append(WritingEvent(kind="paste", size=size))
            if size >= self.cards.limits["paste_alert_chars"]:
                self.alert("paste", "6", f"{size}자 붙여넣기")
        if accessibility and not any(e.kind == "accessibility" for e in a.events):
            a.events.append(WritingEvent(kind="accessibility", detail="글자 확대 등"))
        a.temp_draft, a.temp_saved_at = body, now()
        return {"chars": official_count(body), "cells": cells, "saved_at": a.temp_saved_at}

    def help_request(self, text: str) -> str:
        a = self.need()
        self._ensure_stage("6")
        a.events.append(WritingEvent(kind="help", detail=text[:300]))
        if _FUNCTION_Q.search(text):
            for pat, ans in FUNCTION_ANSWERS:
                if pat.search(text):
                    return ans
        a.diagnosis.setdefault("help_saved", []).append(text[:300])
        return "제출 후 확인할 항목으로 저장했어요. 지금은 혼자 써 보는 시간이에요."

    def interrupt(self, target: str, reason: str = "") -> None:
        a = self.need()
        self._ensure_stage("6")
        if target not in [s for s in self.cards.order() if self.cards.get(s).kind == "dialogue"]:
            raise MvpError("돌아갈 단계를 골라 주세요.")
        a.events.append(WritingEvent(kind="interrupt", detail=f"{target}: {reason[:200]}"))
        a.diagnosis["condition"] = "interrupted_then_supplemented"
        a.diagnosis["supplementing"] = target
        t = a.stages[target]
        t.status = "in_progress"
        t.turns.append(Turn(role="system", text="6단계 작성을 잠시 멈추고 보충하러 왔어요. 초고는 그대로 보관돼 있어요."))
        a.current = target

    def _new_draft(self, kind: str, body: str, same_as: str | None = None) -> DraftVersion:
        a = self.need()
        d = DraftVersion(id=f"{kind[:3]}-{len(a.drafts) + 1}", kind=kind, body=body, chars=official_count(body),
                         cells=cells_used(body), condition=a.diagnosis.get("condition", "independent_after_support"),
                         same_as=same_as)
        a.drafts.append(d)
        return d

    def complete_draft(self) -> DraftVersion:
        a = self.need()
        self._ensure_stage("6")
        if a.draft("independent"):
            raise MvpError("독립 초고는 이미 고정됐어요.")
        if official_count(a.temp_draft) < 50:
            raise MvpError("초고를 조금 더 써 주세요. (50자 이상)")
        return self._new_draft("independent", a.temp_draft)

    def submit_selfcheck(self, entries: list[dict], confident: str, uncertain: str) -> SelfCheck:
        a = self.need()
        self._ensure_stage("6")
        d = a.draft("independent")
        if not d:
            raise MvpError("먼저 ‘초고 완성’을 눌러 주세요.")
        if a.selfcheck:
            raise MvpError("자기검증 기록은 이미 저장됐어요.")
        keys = [c.key for c in self.cards.get("6").selfcheck]
        got = {e["key"]: e for e in entries}
        out = []
        for k in keys:
            e = got.get(k)
            if not e or e.get("judgment") not in ("problem", "keep"):
                raise MvpError("다섯 항목 모두 ‘문제 있음’ 또는 ‘유지’를 골라 주세요.")
            quote = (e.get("quote") or "").strip()
            reason = (e.get("reason") or "").strip()
            if e["judgment"] == "keep" and (not quote or not reason):
                raise MvpError("‘유지’를 고른 항목은 확인한 구절과 유지 이유를 적어야 해요.")
            if e["judgment"] == "problem" and not reason:
                raise MvpError("‘문제 있음’을 고른 항목은 이유를 적어 주세요.")
            start = d.body.find(quote) if quote else -1
            out.append(SelfCheckEntry(key=k, judgment=e["judgment"], reason=reason[:300], quote=quote[:200],
                                      start=start if start >= 0 else None,
                                      end=start + len(quote) if start >= 0 else None))
        if not confident.strip() or not uncertain.strip():
            raise MvpError("가장 자신 있는 부분과 가장 불확실한 부분을 적어 주세요.")
        a.selfcheck = SelfCheck(draft_id=d.id, entries=out, confident=confident.strip()[:300],
                                uncertain=uncertain.strip()[:300])
        a.temp_draft = d.body
        return a.selfcheck

    def save_pre_revision(self, body: str) -> DraftVersion:
        a = self.need()
        self._ensure_stage("6")
        d = a.draft("independent")
        if not a.selfcheck or not d:
            raise MvpError("자기검증을 먼저 마쳐 주세요.")
        if a.draft("pre_revision"):
            raise MvpError("선행 수정본은 이미 저장됐어요.")
        body = body.replace("\r", "")
        if cells_used(body) > MAX_CELLS:
            raise MvpError("원고지 800칸을 넘었어요.")
        if body == d.body:
            return self._new_draft("pre_revision", body, same_as=d.id)
        return self._new_draft("pre_revision", body)

    def submit(self) -> DraftVersion:
        a = self.need()
        r = self._ensure_stage("6")
        pre = a.draft("pre_revision")
        if not pre:
            raise MvpError("자기검증 후 수정본을 먼저 저장해 주세요.")
        if a.draft("submitted"):
            raise MvpError("이미 제출했어요.")
        d = self._new_draft("submitted", pre.body)
        if a.writing_started:
            from datetime import datetime
            a.writing_seconds = (datetime.fromisoformat(d.ts) - datetime.fromisoformat(a.writing_started)).total_seconds()
        a.diagnosis["handoff"] = {"pack": f"{self.pack.id}@{self.pack.version}", "rubric": self.rubric.full_id,
                                  "submitted_at": d.ts, "condition": d.condition, "chars": d.chars,
                                  "uncertain": a.selfcheck.uncertain if a.selfcheck else ""}
        r.status, r.finished_at = "completed", now()
        ev = self.grade(d)                             # 즉시 채점, 결과는 자기진단 후 공개
        self.generate_annotations(ev, d)
        a.current = "6.1"
        s61 = a.stages["6.1"]
        s61.status, s61.started_at = "in_progress", now()
        a.review_phase = "diagnose"
        return d

    # ------------------------------------------------------------------ 채점 (8-2)
    def grade(self, d: DraftVersion, replaces: str | None = None, note: str = "") -> Evaluation:
        a = self.need()
        g = self.roles["grader"]
        # 2회 독립 채점을 동시에 실행한다 (AI 채점 1회가 수십 초 걸려 차례로 하면 서버 한도를 넘는다)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            runs = list(pool.map(lambda _: g.grade(self.pack, self.rubric, d.body), range(2)))
        for items in runs:
            if fix_evidence(d.body, items):           # 인용을 못 찾으면 한 번 다시 채점
                items[:] = g.grade(self.pack, self.rubric, d.body)
                fix_evidence(d.body, items)
        merged, mismatch = merge_runs(runs)
        n = 2
        if mismatch:
            third = g.grade(self.pack, self.rubric, d.body)
            fix_evidence(d.body, third)
            merged, _ = merge_runs(runs + [third])
            for it in merged:
                it.review_recommended = it.code in mismatch
            n = 3
            self.alert("grading_mismatch", "6.1", f"{d.kind} 채점 불일치: {', '.join(mismatch)}")
        calc = compute(self.rubric, merged, d.chars, self.pack.max_chars)
        ev = Evaluation(id=f"ev-{len(a.evaluations) + 1}", draft_id=d.id, rubric_version=self.rubric.full_id,
                        evaluator=f"ai:{getattr(g, 'name', 'grader')}", items=merged, runs=n, replaces=replaces,
                        note=note, **calc)
        a.evaluations.append(ev)
        return ev

    # ------------------------------------------------------------------ 첨삭 표시 (8-3·8-4)
    def generate_annotations(self, ev: Evaluation, d: DraftVersion) -> list[Annotation]:
        a = self.need()
        flagged_keys = {e.key for e in (a.selfcheck.entries if a.selfcheck else []) if e.judgment == "problem"}
        self_area = {"tasks": "A", "evidence": "B", "scope": "B", "form": "E", "length": "E"}
        self_areas = {self_area.get(k) for k in flagged_keys}
        cands = []
        for it in ev.items:
            ri = self.rubric.item(it.code)
            if it.level is None or it.level >= 4:
                continue
            cands.append((ri.priority, 0 if ri.area in self_areas else 1, it.level, it, ri))
        cands.sort(key=lambda x: (x[0], x[1], x[2]))
        anns = []
        for n, (_, _, _, it, ri) in enumerate(cands, start=1):
            if it.evidence:
                e = it.evidence[0]
                anchor = {"draft_id": d.id, "start": e["start"], "end": e["end"], "quote": e["quote"]}
                mark = "strike" if it.error_code else "underline"
            else:
                anchor = {"draft_id": d.id, "start": len(d.body), "end": len(d.body), "quote": ""}
                mark = "insert"
            anns.append(Annotation(number=n, rubric_refs=[it.code], anchor=anchor, mark_type=mark,
                                   nature="optional_improvement" if ri.area == "E" else "correction",
                                   margin_note=ri.margin_question, shown=n <= 3))
        strong = [it for it in ev.items if it.level == 4 and it.evidence and it.code not in ("E1", "E2")]
        if strong:
            it = strong[0]
            e = it.evidence[0]
            anns.append(Annotation(number=len(anns) + 1, rubric_refs=[it.code], nature="strength", mark_type="circle",
                                   anchor={"draft_id": d.id, "start": e["start"], "end": e["end"], "quote": e["quote"]},
                                   margin_note=f"유지할 강점: {self.rubric.item(it.code).name}", shown=True))
        a.annotations = anns
        return anns

    def annotation(self, number: int) -> Annotation:
        ann = next((x for x in self.need().annotations if x.number == number), None)
        if not ann:
            raise MvpError("첨삭 항목을 찾을 수 없어요.")
        return ann

    # ------------------------------------------------------------------ 6-1 진행 (8-1)
    def submit_diagnosis(self, confident: str, uncertain: str, paragraph_map: dict[str, str]) -> None:
        a = self.need()
        self._ensure_stage("6.1")
        a.diagnosis["self"] = {"confident": confident.strip()[:300], "uncertain": uncertain.strip()[:300],
                               "paragraph_map": paragraph_map}
        a.review_phase = "results"

    def to_threads(self) -> None:
        a = self.need()
        if a.review_phase == "results":
            a.review_phase = "threads"
        for ann in a.annotations:
            if ann.nature != "strength" and not ann.thread:
                ann.thread.append(ThreadTurn(role="tutor", step=0, text=roles_mod.thread_question(
                    0, circled(ann.number), ann.anchor.get("quote", ""), ann.margin_note)))

    def thread_reply(self, number: int, text: str) -> ThreadTurn:
        ann = self.annotation(number)
        text = text.strip()
        if not text:
            raise MvpError("답을 입력해 주세요.")
        if ann.status in ("withdrawn", "resolved"):
            raise MvpError("이미 정리된 항목이에요.")
        ann.thread.append(ThreadTurn(role="student", text=text[:1000], step=ann.thread_step))
        if roles_mod.thread_stalled(text):
            ann.stalls += 1
            if ann.stalls == 1:
                ann.support_steps.append("보완 질문")
                q = "괜찮아요. 해당 문장을 소리 내어 읽고, 가장 중요한 낱말 하나만 골라 볼까요?"
            elif ann.stalls == 2:
                ann.support_steps.append("설명 지원")
                ri = self.rubric.item(ann.rubric_refs[0])
                q = f"도움말: 이 항목은 ‘{ri.name}’을 보는 곳이에요. 이 점을 생각하며 고칠지 유지할지 판단해 볼까요?"
                ann.thread_step = 3
            else:
                ann.status = "unresolved"
                q = "이 항목은 ‘미해결’로 남겨 둘게요. 다음 항목으로 넘어가도 괜찮아요."
        else:
            ann.stalls = 0
            if ann.thread_step == 0:
                ann.support_steps.append("핵심 질문")
            ann.thread_step = min(ann.thread_step + 1, 3 if ann.decision is None else 4)
            q = roles_mod.thread_question(ann.thread_step, circled(ann.number), ann.anchor.get("quote", ""),
                                          ann.margin_note)
        t = ThreadTurn(role="tutor", text=q, step=ann.thread_step)
        ann.thread.append(t)
        return t

    def decide(self, number: int, decision: str, reason: str, revision: str = "") -> Annotation:
        ann = self.annotation(number)
        if decision not in ("accept", "partial", "reject"):
            raise MvpError("판단을 골라 주세요.")
        reason = reason.strip()
        if not reason:
            raise MvpError("판단한 이유를 적어 주세요.")
        ann.history.append({"status": ann.status, "decision": ann.decision, "ts": now()})
        ann.decision, ann.decision_reason = decision, reason[:500]
        if revision.strip():
            ann.revision_link = {"proposal": revision.strip()[:500]}
        if decision == "reject":
            valid = bool(re.search(r"[가나다]\s*-\s*\d", reason)) or len(reason) >= 25
            ann.status = "withdrawn" if valid else "active"
            msg = ("설명이 타당해요. 이 표시는 거둘게요." if valid
                   else "유지하려는 근거를 제시문 문단과 함께 조금 더 적어 주면 다시 판단할게요.")
        elif decision == "partial":
            ann.status, msg = "adjusted", "일부만 받아들이는 판단을 기록했어요. 최종본에서 그렇게 고쳐 보세요."
        else:
            msg = "받아들이는 판단을 기록했어요. 최종본에서 내 문장으로 고쳐 보세요."
        ann.thread_step = 4
        ann.thread.append(ThreadTurn(role="tutor", text=msg, step=4))
        return ann

    def appeal(self, target: str, reason: str) -> Appeal:
        a = self.need()
        if not reason.strip():
            raise MvpError("이의 제기 이유를 적어 주세요.")
        ap = Appeal(target=target, reason=reason.strip()[:500])
        a.appeals.append(ap)
        if target.startswith("eval:"):
            code = target.split(":", 1)[1]
            d = a.draft("final") or a.draft("submitted")
            prev = a.latest_eval(d.id)
            again = next((i for i in self.roles["grader"].grade(self.pack, self.rubric, d.body) if i.code == code), None)
            old = next((i for i in prev.items if i.code == code), None) if prev else None
            if again and old and again.level != old.level:
                items = [i.model_copy(deep=True) for i in prev.items]
                for i, it in enumerate(items):
                    if it.code == code:
                        items[i] = again
                calc = compute(self.rubric, items, d.chars, self.pack.max_chars)
                ev = Evaluation(id=f"ev-{len(a.evaluations) + 1}", draft_id=d.id, rubric_version=prev.rubric_version,
                                evaluator=prev.evaluator, items=items, replaces=prev.id,
                                note=f"이의 제기 재검토: {code} {old.level}→{again.level}", **calc)
                a.evaluations.append(ev)
                ap.status, ap.result = "done", ev.note
                return ap
        ap.status, ap.result = "reviewing", "선생님 검토 대기열로 보냈어요."
        self.alert("appeal", "6.1", f"{target}: {ap.reason[:60]}")
        return ap

    def to_revise(self) -> None:
        a = self.need()
        if a.review_phase not in ("threads", "results"):
            raise MvpError("지금은 수정본을 쓸 수 없어요.")
        a.review_phase = "revise"
        if not a.temp_draft or a.temp_draft == (a.draft("pre_revision").body if a.draft("pre_revision") else ""):
            a.temp_draft = a.draft("submitted").body            # 결정 4 권장안: 제출본 본문을 미리 채움

    def submit_final(self, body: str) -> Evaluation:
        a = self.need()
        self._ensure_stage("6.1")
        if a.review_phase != "revise":
            raise MvpError("수정본 작성 단계가 아니에요.")
        body = body.replace("\r", "")
        if cells_used(body) > MAX_CELLS:
            raise MvpError("원고지 800칸을 넘었어요.")
        if official_count(body) < 50:
            raise MvpError("최종본을 조금 더 써 주세요.")
        sub = a.draft("submitted")
        fin = self._new_draft("final", body)
        ev = self.grade(fin)
        self._link_revisions(sub, fin)
        self._check_ai_copy(fin)
        for ann in a.annotations:
            if ann.nature != "strength" and ann.status == "active":
                ann.status = "unresolved" if ann.decision is None else "resolved"
            elif ann.status == "adjusted":
                ann.status = "resolved"
        self._classify_selfcheck()
        a.review_phase = "compare"
        return ev

    def _link_revisions(self, sub: DraftVersion, fin: DraftVersion) -> None:
        sm = difflib.SequenceMatcher(None, sub.body, fin.body, autojunk=False)
        for ann in self.need().annotations:
            prop = (ann.revision_link or {}).get("proposal", "")
            if prop and (i := fin.body.find(prop)) >= 0:
                ann.revision_link = {**ann.revision_link, "draft_id": fin.id, "start": i, "end": i + len(prop),
                                     "method": "proposal"}
                continue
            s, e = ann.anchor.get("start", 0), ann.anchor.get("end", 0)
            if e <= s:
                continue
            blocks = [b for b in sm.get_matching_blocks() if b.size and b.a < e and b.a + b.size > s]
            covered = sum(min(e, b.a + b.size) - max(s, b.a) for b in blocks)
            if blocks and covered / (e - s) >= 0.5:
                b0, b1 = blocks[0], blocks[-1]
                ns = b0.b + max(0, s - b0.a)
                ne = b1.b + min(b1.size, e - b1.a)
                ann.revision_link = {**(ann.revision_link or {}), "draft_id": fin.id, "start": ns, "end": ne,
                                     "method": "diff", "confidence": round(covered / (e - s), 2)}
            else:
                ann.revision_link = {**(ann.revision_link or {}), "draft_id": fin.id, "start": None, "end": None,
                                     "method": "none", "note": "대응 구절 없음"}

    def _check_ai_copy(self, fin: DraftVersion) -> None:
        """최종본에 AI 예시 문장(사다리 5 부분 예시·예시답안)과 거의 같은 문장이 있으면 교사 화면에 표시."""
        a = self.need()
        ai_texts = [t.text for r in a.stages.values() for t in r.turns if t.role == "tutor"
                    and t.judgment and t.judgment.scaffold_level >= 5]
        ai_texts += [m.text for m in self.pack.model_answers]
        for s in sentences(fin.body):
            if any(containment(s, ref) >= 0.8 for ref in ai_texts if len(s) >= 15):
                self.alert("ai_copy", "6.1", f"AI 예시와 거의 같은 문장: {s[:50]}")
                a.diagnosis["ai_copy"] = True
                break

    def _classify_selfcheck(self) -> None:
        """6단계 자기교정 결과 네 분류 (채점 결과와 대조해 확정)."""
        a = self.need()
        if not a.selfcheck:
            return
        ind, pre = a.draft("independent"), a.draft("pre_revision")
        sub_ev = a.latest_eval(a.draft("submitted").id)
        area_of = {"tasks": "A", "evidence": "B", "scope": "B", "form": "E", "length": "E"}
        res = {}
        for e in a.selfcheck.entries:
            changed = bool(pre and ind and pre.same_as is None and e.quote and e.quote not in pre.body)
            weak = any(i.level is not None and i.level <= 2 and self.rubric.item(i.code).area == area_of.get(e.key)
                       for i in (sub_ev.items if sub_ev else []))
            if e.judgment == "problem":
                res[e.key] = "found_and_fixed" if changed else "found_unresolved"
            else:
                res[e.key] = "insufficient_check" if weak else "checked_and_kept"
        a.selfcheck_result = res

    def finish_review(self, next_question: str) -> None:
        a = self.need()
        if a.review_phase != "compare":
            raise MvpError("재평가 비교를 먼저 확인해 주세요.")
        if not next_question.strip():
            raise MvpError("다음 글에서 쓸 점검 질문을 적어 주세요.")
        a.next_check_question = next_question.strip()[:300]
        a.review_phase = "done"
        r = a.stages["6.1"]
        r.status, r.finished_at = "completed", now()
        a.reflection = a.reflection or Reflection(version=str(reflection_items()["version"]))

    def model_answer_open(self) -> bool:
        """예시답안은 6-1 최종본 확정 후에만 선택 열람 (12장)."""
        a = self.need()
        return a.review_phase in ("compare", "done") and a.draft("final") is not None

    # ------------------------------------------------------------------ 돌아보기 (9장)
    def save_reflection(self, answers: dict, submit: bool = False, skip: bool = False) -> Reflection:
        a = self.need()
        if a.review_phase != "done":
            raise MvpError("평가·첨삭을 마친 뒤에 돌아볼 수 있어요.")
        ref = a.reflection or Reflection(version=str(reflection_items()["version"]))
        personal = {i["id"] for i in reflection_items()["items"] if i["store"] == "personal"}
        clean = {k: v for k, v in answers.items() if k in personal}
        if skip:
            ref.status = "skipped"
        else:
            if ref.status == "submitted" and ref.first_answers is None:
                ref.first_answers = dict(ref.answers)
            ref.answers = clean
            ref.status = "submitted" if submit else ("draft" if ref.status != "submitted" else "submitted")
            if submit and not ref.first_submitted_at:
                ref.first_submitted_at = now()
        ref.updated_at = now()
        a.reflection = ref
        if submit or skip:
            a.status, a.finished_at = "done", a.finished_at or now()
        return ref

    # ------------------------------------------------------------------ 교사 (11·12장)
    def teacher_allow(self, stage: str, action: str, who: str, note: str = "") -> None:
        a = self.need()
        r = a.stages[stage]
        r.teacher_override = f"{action} by {who}: {note}"[:300]
        if action == "resume":
            r.status = "in_progress" if any(v.status not in ("met", "skipped") for v in r.subgoals.values()) else "summarizing"
        elif action == "complete":
            self._complete_stage(r)
        self.audit(who, f"stage_{action}", stage)

    def teacher_regrade(self, eval_id: str, code: str, level: int | None, reason: str, who: str) -> Evaluation:
        a = self.need()
        if not reason.strip():
            raise MvpError("수정 이유를 적어 주세요.")
        prev = next((e for e in a.evaluations if e.id == eval_id), None)
        if not prev:
            raise MvpError("평가를 찾을 수 없어요.")
        items = [i.model_copy(deep=True) for i in prev.items]
        for it in items:
            if it.code == code:
                it.reason = f"[교사] {reason.strip()} (이전 수준 {it.level})"
                it.level = level
                it.review_recommended = False
        d = a.draft_by_id(prev.draft_id)
        calc = compute(self.rubric, items, d.chars if d else 0, self.pack.max_chars)
        ev = Evaluation(id=f"ev-{len(a.evaluations) + 1}", draft_id=prev.draft_id, rubric_version=prev.rubric_version,
                        evaluator=f"teacher:{who}", items=items, replaces=prev.id, note=reason.strip()[:300], **calc)
        a.evaluations.append(ev)
        self.audit(who, "regrade", f"{eval_id}:{code}")
        return ev

    def teacher_alert(self, idx: int, status: str, note: str, who: str) -> None:
        a = self.need()
        if not 0 <= idx < len(a.alerts) or status not in ("received", "reviewing", "done", "held"):
            raise MvpError("알림을 찾을 수 없어요.")
        if status == "held" and not note.strip():
            raise MvpError("보류 이유를 적어 주세요.")
        a.alerts[idx].status, a.alerts[idx].note = status, note.strip()[:300]
        self.audit(who, f"alert_{status}", str(idx))

    def teacher_note(self, text: str, who: str) -> None:
        a = self.need()
        if text.strip():
            a.teacher_notes.append({"by": who, "text": text.strip()[:1000], "ts": now()})
            self.audit(who, "note")


def score_rows(rubric, ev: Evaluation) -> list[dict]:
    rows = []
    for ri in rubric.items:
        it = next((i for i in ev.items if i.code == ri.code), None) or EvalItem(code=ri.code, level=None)
        rows.append({"item": ri, "eval": it})
    return rows
