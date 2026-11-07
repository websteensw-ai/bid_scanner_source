"""공통 실행 틀 (Z-047·Z-048·Z-014).

모든 학습 주제(L1~L5)와 보충 경로(S1~S5)는 이 엔진 하나로 운영된다.
교수 순서: 과제 안내 → 짧은 자력 시도 → 응답 진단 → 필요한 지원 → 재수행 → 확인 또는 이동.

정책 (AI 가 아니라 시스템이 처리, Z-049)
- 최초 수행 전에는 답·해설을 공개하지 않는다 (Z-015). 지원 문구는 승인된 첫 질문·설명·시범만 쓴다.
- 같은 판단점의 방향 질문은 2회까지. 개념 미이해가 분명하면 바로 설명 → 시범으로 전환 (Z-018)
- 지원 후 수행은 독립 수행으로 기록하지 않는다 (Z-017, levels.level_after)
- 충분한 답이면 다음 단계의 같은 기준 확인을 생략한다 (Z-008·L1-012)
- 독립 확인 단계에서는 어휘 외 도움을 주지 않는다 (L1-018)
- 판정이 불확실하면 확인 질문 1회, 그래도 불확실하면 미확인 + 교사 검토 (Z-017·Z-030)
- 같은 보충 경로는 한 번만 (S1-011·S2-011). 반복 대신 교사 검토로 연결 (Z-036)
"""
import time
from collections import defaultdict

from src.learning.analyzer import Analyzer, diagnose
from src.learning.content import Bundle, ContentPack, Step, active_version, count_chars, load_pack
from src.learning.entry import EntryDecision, judge_entry
from src.learning.intent import ANSWER, ANSWER_REQUEST, QUESTION
from src.learning.levels import (
    CRITERION_SUPPLEMENT,
    Criterion,
    Level,
    SupportType,
    level_after,
)
from src.learning.state import (
    Attempt,
    CriterionRecord,
    Flag,
    LearnerState,
    Message,
    ReviewRecord,
    SessionState,
    StepState,
    SupportRecord,
    now,
)

MAX_DIRECTIONS_PER_POINT = 2
OFF_TASK_FLAG_AT = 3        # 무관한 발화가 이 횟수에 이르면 휴식 권유 + 교사 알림 (Z-030·Z-036)
CONFIRM_QUESTION = "그렇게 생각한 이유를 제시문의 어느 부분에서 찾았는지 한 문장으로 알려 줄래요?"
CONTENT_SUPPORTS = {SupportType.GUIDE, SupportType.DIRECTION, SupportType.STRUCTURE,
                    SupportType.EXPLANATION, SupportType.DEMO}
NO_HELP_KINDS = {"draft"}


class LearningError(Exception):
    pass


def answered(ss: StepState) -> list[Attempt]:
    """과제에 대한 실제 답(최초·수정)만. 무관한 발화·질문은 제외."""
    return [a for a in ss.attempts if a.kind in ("first", "revised")]


def _first_sentence(text: str) -> str:
    for sep in (". ", "? ", "요. "):
        if sep in text:
            return text.split(sep)[0] + sep.strip()
    return text


class Engine:
    def __init__(self, state: LearnerState, analyzer: Analyzer,
                 suspended: set[str] | None = None):
        self.state = state
        self.analyzer = analyzer
        self.suspended = suspended or set()     # 사용 중지된 묶음·제시문 id (P-014)

    # ---------- 조회 ----------
    def pack(self, session: SessionState | None = None) -> ContentPack:
        return load_pack(session.version if session else active_version())

    def bundle(self, session: SessionState) -> Bundle:
        return self.pack(session).bundles[session.bundle_id]

    def current_step(self, session: SessionState) -> Step | None:
        b = self.bundle(session)
        return b.steps[session.step_idx] if session.step_idx < len(b.steps) else None

    def step_state(self, session: SessionState) -> StepState | None:
        step = self.current_step(session)
        return session.steps.get(step.id) if step else None

    # ---------- 세션 ----------
    def start(self, bundle_id: str) -> SessionState:
        """진행 중이면 이어서, 아니면 현재 승인 버전으로 새로 시작 (P-025)."""
        existing = self.state.sessions.get(bundle_id)
        if existing and existing.status != "done":
            if existing.status == "paused":
                existing.status = "active"
                self.state.log("resume", bundle_id, step=existing.step_idx)
            return existing
        if existing and existing.status == "done":
            return existing
        pack = self.pack()
        bundle = pack.bundles[bundle_id]
        if bundle.status != "approved" or bundle_id in self.suspended:
            raise LearningError("이 학습은 지금 사용할 수 없어요. 선생님께 문의해 주세요.")
        if bundle.kind == "supplement" and bundle_id in self.state.supplements_done:
            raise LearningError("이미 진행한 보충이에요. 같은 보충은 반복하지 않아요.")
        session = SessionState(key=bundle_id, bundle_id=bundle_id, version=pack.version)
        self.state.sessions[bundle_id] = session
        self.state.log("start", bundle_id, version=pack.version)
        self._enter_step(session)
        return session

    def pause(self, session: SessionState) -> None:
        """답안과 진행 위치를 저장하고 중단 (Z-020·L3-002)."""
        session.status = "paused"
        self.state.log("pause", session.key, step=session.step_idx)

    def save_draft(self, session: SessionState, text: str) -> None:
        """작성 중 임시 저장. 제출·분석 없이 원고와 위치만 보존 (Z-020·L5-016)."""
        step = self.current_step(session)
        if step:
            session.outputs[step.id] = text
            self.state.log("draft_saved", session.key, step=step.id, chars=count_chars(text))

    def topic_status(self, bundle_id: str) -> str:
        s = self.state.sessions.get(bundle_id)
        return s.status if s else "todo"

    # ---------- 단계 진입 ----------
    def _should_skip(self, session: SessionState, step: Step) -> str | None:
        required = [c.id for c in step.criteria if c.required]
        if step.skip_if_met and required and all(c in session.met for c in required):
            return "앞 활동에서 이미 확인됨"
        if step.only_if_independent:
            done = [s for s in session.steps.values() if s.status == "done" and s.level is not None]
            if any(s.level < Level.INDEPENDENT for s in done):
                return "기본 활동에서 지원을 받아 추가 확인 과제는 생략"
        return None

    def _enter_step(self, session: SessionState) -> None:
        b = self.bundle(session)
        while session.step_idx < len(b.steps):
            step = b.steps[session.step_idx]
            if step.id in session.steps:          # 재개
                return
            reason = self._should_skip(session, step)
            if reason:
                session.steps[step.id] = StepState(step_id=step.id, status="skipped")
                self.state.log("skip", session.key, step=step.id, reason=reason)
                session.step_idx += 1
                continue
            ss = StepState(step_id=step.id)
            if step.prefill_from and ":" in step.prefill_from:
                ob, _, ostep = step.prefill_from.rpartition(":")
                other = self.state.sessions.get(ob)
                if other and ostep in other.outputs:
                    session.outputs.setdefault(step.id, other.outputs[ostep])
            if step.prefill_from and step.prefill_from in session.outputs:
                session.outputs.setdefault(step.id, session.outputs[step.prefill_from])
                src = next((s for s in b.steps if s.id == step.prefill_from), None)
                if src and src.kind == "self_review":
                    before = session.outputs.get(src.prefill_from or "", "")
                    if before.strip() != session.outputs[step.prefill_from].strip():
                        # 학생이 스스로 찾은 수정을 먼저 인정 (L5-040)
                        ss.messages.append(Message(
                            role="tutor", kind="ack",
                            text="제출 전에 스스로 점검해서 직접 고친 부분이 있어요. "
                                 "스스로 찾아낸 수정으로 기록해 둘게요."))
            session.steps[step.id] = ss
            return
        self._finish(session)

    def _advance(self, session: SessionState) -> None:
        session.step_idx += 1
        self._enter_step(session)

    def carry(self, session: SessionState, step: Step) -> list[tuple[str, str, str]]:
        """앞 산출물 (이름, 최초 답, 최종 답). 같은 내용을 다시 입력시키지 않는다 (Z-009)."""
        out = []
        for ref in step.carry_from:
            bundle_id, _, step_id = ref.rpartition(":")
            src = self.state.sessions.get(bundle_id) if bundle_id else session
            if not src or step_id not in src.outputs:
                continue
            title = self.pack(src).step(src.bundle_id, step_id).title
            out.append((title, src.first_outputs.get(step_id, ""), src.outputs[step_id]))
        return out

    # ---------- 도움 요청 ----------
    def help_options(self, session: SessionState) -> list[str]:
        step = self.current_step(session)
        if not step or step.kind in NO_HELP_KINDS:
            return []
        opts = ["vocab"] if step.vocab else []
        if step.independent_check or step.allow_one_direction:
            return opts                          # 내용 힌트 없음 (L1-018)
        ss = session.steps[step.id]
        if not answered(ss):
            # 최초 수행 전에는 과제 안내까지만 (답·해설 비공개, Z-015)
            return opts + (["guide"] if step.guide else []) + ["dont_know"]
        return (opts + (["guide"] if step.guide else []) + (["structure"] if step.structure else [])
                + ["dont_know"])

    def request_help(self, session: SessionState, kind: str, word: str | None = None) -> None:
        step = self.current_step(session)
        ss = session.steps[step.id]
        if kind not in self.help_options(session):
            raise LearningError("지금은 이 도움을 받을 수 없어요.")
        if kind == "vocab":
            meaning = step.vocab.get(word or "", "")
            self._support(session, ss, SupportType.VOCAB, f"‘{word}’: {meaning}", point=word or "")
        elif kind == "guide":
            self._support(session, ss, SupportType.GUIDE, step.guide)
        elif kind == "structure":
            self._support(session, ss, SupportType.STRUCTURE, step.structure)
        elif kind == "dont_know":
            ss.messages.append(Message(role="student", text="잘 모르겠어요.", kind="help"))
            if not self._escalate(session, step, ss, point="concept"):
                ss.messages.append(Message(role="tutor", kind="prompt",
                                           text="설명과 시범을 참고해서 떠오르는 만큼만 써 보세요. "
                                                "완벽하지 않아도 괜찮아요."))

    def _support(self, session, ss: StepState, type_: SupportType, text: str, point: str = "") -> None:
        ss.supports.append(SupportRecord(type=type_, point=point, text=text))
        ss.messages.append(Message(role="tutor", text=text, kind=type_.value))
        self.state.log("support", session.key, step=ss.step_id, type=type_.value, point=point)

    def _escalate(self, session, step: Step, ss: StepState, point: str) -> bool:
        """설명 → 시범 순으로 집중 지원. 더 줄 것이 없으면 False."""
        if not ss.explained and step.explanation:
            ss.explained = True
            self._support(session, ss, SupportType.EXPLANATION, step.explanation, point)
            ss.messages.append(Message(role="tutor", kind="prompt",
                                       text="설명을 참고해서 원래 과제를 직접 다시 해 볼까요?"))
            return True
        if not ss.demoed and step.demo:
            ss.demoed = True
            self._support(session, ss, SupportType.DEMO, step.demo.text, point)
            ss.messages.append(Message(role="tutor", kind="prompt",
                                       text="시범은 다른 글이에요. 이제 원래 제시문으로 직접 해 보세요."))
            return True
        return False

    # ---------- 제출 ----------
    def submit(self, session: SessionState, answer: str, evidence: str = "",
               choice: str | None = None) -> None:
        if session.status == "done":
            raise LearningError("이미 마친 학습이에요.")
        step = self.current_step(session)
        ss = session.steps[step.id]
        session.status = "active"
        try:
            shown = time.mktime(time.strptime(ss.shown_at[:19], "%Y-%m-%dT%H:%M:%S"))
            ss.active_seconds += max(0.0, min(time.time() - shown, 1800))
        except ValueError:
            pass

        if step.kind in ("info",):
            ss.status = "done"
            self._advance(session)
            return
        if step.kind in ("outline", "draft", "self_review"):
            self._submit_writing(session, step, ss, answer, evidence)
            return
        self._submit_task(session, step, ss, answer, evidence, choice)
        ss.shown_at = now()

    def _submit_writing(self, session, step: Step, ss: StepState, text: str, note: str) -> None:
        """개요·초고·자기검토: AI 내용 개입 없음 (L5-032~034). 모든 판본을 따로 보존 (L5-036·L5-039)."""
        if not text.strip():
            raise LearningError("내용을 입력해 주세요.")
        kind = "first" if not ss.attempts else "revised"
        ss.attempts.append(Attempt(text=text, evidence=note, kind=kind))
        session.outputs[step.id] = text
        session.first_outputs.setdefault(step.id, text)
        ss.messages.append(Message(role="student", text=text, kind="answer"))
        extra = {}
        if step.max_chars:
            extra["chars"] = count_chars(text)
        if step.kind == "self_review" and step.prefill_from:
            before = session.outputs.get(step.prefill_from, "")
            extra["self_revised"] = before.strip() != text.strip()
            extra["reason"] = note
        self.state.log(f"{step.kind}_saved", session.key, step=step.id, **extra)
        ss.status = "done"
        if step.done_message:
            ss.messages.append(Message(role="tutor", text=step.done_message, kind="done"))
        self._advance(session)

    def _submit_task(self, session, step: Step, ss: StepState, answer: str, evidence: str,
                     choice: str | None) -> None:
        if not answer.strip() and not choice:
            raise LearningError("답을 입력해 주세요.")
        supports = [s.type for s in ss.supports]
        excerpts = [self.pack(session).excerpts[e] for e in step.excerpts]
        context = {label: final for label, _first, final in self.carry(session, step)}

        # 분량 초과: 내용 분석 전에 학생이 직접 줄이도록 안내 (L5-016·L5-050). 원고는 그대로 저장
        if step.max_chars and count_chars(answer) > step.max_chars \
                and ss.directions.get("length", 0) < MAX_DIRECTIONS_PER_POINT:
            ss.attempts.append(Attempt(text=answer, kind="first" if not answered(ss) else "revised",
                                       supports_before=supports, error="length"))
            session.outputs[step.id] = answer
            ss.messages.append(Message(role="student", text=answer, kind="answer"))
            ss.directions["length"] = ss.directions.get("length", 0) + 1
            if "length" not in session.errors_seen:
                session.errors_seen.append("length")
            self._support(session, ss, SupportType.DIRECTION,
                          f"지금 {count_chars(answer)}자예요. 원고는 그대로 저장했어요. "
                          "중심 주장과 관계없는 내용, 반복된 문장, 너무 긴 제시문 설명이나 사례를 "
                          "순서대로 살펴보고 직접 줄여 보세요. 반론에 대한 조건과 근거는 남겨 두세요.",
                          point="length")
            return

        t0 = time.time()
        diag = diagnose(self.analyzer, step, answer, evidence, choice, excerpts, context)
        ss.ai_wait_seconds += time.time() - t0
        if diag.intent != ANSWER:
            self._handle_non_answer(session, step, ss, answer, diag)
            return

        att = Attempt(text=answer, evidence=evidence, choice=choice,
                      kind="first" if not answered(ss) else "revised",
                      supports_before=supports, met=diag.met, error=diag.primary_error,
                      rationale=diag.rationale)
        ss.attempts.append(att)
        shown = answer + (f"\n(근거: {evidence})" if evidence else "")
        if choice:
            shown = f"[{choice}] {shown}"
        ss.messages.append(Message(role="student", text=shown, kind="answer"))
        session.first_outputs.setdefault(step.id, answer)
        session.outputs[step.id] = answer
        self.state.log("answer", session.key, step=step.id, kind=att.kind, met=diag.met,
                       error=diag.primary_error, analyzer=self.analyzer.name)

        required = [c.id for c in step.criteria if c.required]
        met_all = all(c in diag.met for c in required)
        content_supports = [s for s in supports if s in CONTENT_SUPPORTS]

        if diag.primary_error:
            if diag.primary_error not in session.errors_seen:
                session.errors_seen.append(diag.primary_error)
            err = next(e for e in step.errors if e.id == diag.primary_error)
            if err.major and not met_all:
                session.major_error = True

        # 1) 충족
        if met_all:
            lvl = level_after(supports)
            if step.allow_one_direction and content_supports:
                lvl = min(lvl, Level.MINIMAL)
            self._complete(session, step, ss, lvl, diag.met)
            return

        # 부분 충족 기준은 그대로 인정 (다음 단계 생략 판단에 사용)
        for c in diag.met:
            session.met.setdefault(c, int(level_after(supports)))

        # 2) 독립 확인: 힌트 없이 결과만 기록
        if step.independent_check:
            if diag.uncertain and ss.confirms == 0:
                self._confirm(session, ss)
                return
            self._close_unconfirmed(session, step, ss, diag.met,
                                    "독립 확인에서 이번에는 확인되지 않음", flag=False)
            return

        # 3) 불확실 → 확인 질문 1회, 그래도 불확실하면 미확인 + 교사 검토
        if diag.uncertain and not diag.concept_gap:
            if ss.confirms == 0:
                self._confirm(session, ss)
                return
            self._close_unconfirmed(session, step, ss, diag.met, "판정 불확실", flag=True)
            return

        point = diag.primary_error or next(c for c in required if c not in diag.met)

        # 4) 재확인(방향 질문 1회 허용)
        if step.allow_one_direction:
            if not content_supports:
                self._direction(session, step, ss, point)
                return
            self._close_unconfirmed(session, step, ss, diag.met, "재확인 수행 미확인", flag=True)
            return

        # 5) 방향 질문 (판단점당 2회) → 설명 → 시범 → 기록 후 이동
        if not diag.concept_gap and ss.directions.get(point, 0) < MAX_DIRECTIONS_PER_POINT:
            self._direction(session, step, ss, point)
            return
        if self._escalate(session, step, ss, point):
            return
        self._close_not_formed(session, step, ss, diag.met)

    # ---------- 답이 아닌 발화 ----------
    def _handle_non_answer(self, session, step: Step, ss: StepState, text: str, diag) -> None:
        """질문·정답 요구·과제와 무관한 말에 즉시 응답하고 과제로 되돌린다.
        정답이나 내용 힌트는 주지 않으며(Z-015), 수준·방향 질문 횟수에 넣지 않는다."""
        ss.attempts.append(Attempt(text=text, kind=diag.intent, rationale=diag.rationale,
                                   supports_before=[s.type for s in ss.supports]))
        ss.messages.append(Message(role="student", text=text, kind=diag.intent))
        self.state.log("non_answer", session.key, step=step.id, intent=diag.intent)
        no_hint = step.independent_check or step.allow_one_direction
        task_line = f"지금 과제는 ‘{step.title}’이에요. {_first_sentence(step.prompt)}"
        help_hint = "" if no_hint else " 막막하면 아래 ‘과제 뜻 알려 주세요’나 ‘잘 모르겠어요’를 눌러도 돼요."

        if diag.intent == QUESTION:
            if diag.asked_word and diag.asked_word in step.vocab:
                self._support(session, ss, SupportType.VOCAB,
                              f"‘{diag.asked_word}’: {step.vocab[diag.asked_word]}", point=diag.asked_word)
                return
            if not no_hint and step.guide:
                self._support(session, ss, SupportType.GUIDE, step.guide, point="question")
                return
            lead = ("이번 과제는 혼자 해 보는 확인이라 내용 힌트는 드릴 수 없어요. " if no_hint
                    else "좋은 질문이에요. ")
            self._support(session, ss, SupportType.REDIRECT,
                          f"{lead}{task_line} 떠오르는 만큼 먼저 써 보면, 그 답을 보고 함께 살펴볼게요.",
                          point="question")
            return

        if diag.intent == ANSWER_REQUEST:
            self._support(session, ss, SupportType.REDIRECT,
                          "정답을 먼저 알려 주지는 않아요. 내가 직접 찾아낸 생각이 진짜 실력이 되거든요. "
                          f"{task_line}{help_hint}", point="answer_request")
            return

        ss.redirects += 1
        if ss.redirects == 1:
            msg = f"앗, 지금 과제와는 다른 이야기 같아요. {task_line}"
        elif ss.redirects < OFF_TASK_FLAG_AT:
            msg = f"다시 과제로 돌아와 볼까요? {task_line}{help_hint}"
        else:
            msg = ("조금 지쳤다면 쉬었다 해도 괜찮아요. ‘저장하고 나가기’를 누르면 지금까지 한 내용이 "
                   f"그대로 남아요. 준비되면 이어서 해요. {task_line}")
            if ss.redirects == OFF_TASK_FLAG_AT:
                self.state.flags.append(Flag(kind="attention", source=f"{session.key}/{step.id}",
                                             detail=f"과제와 무관한 발화 {ss.redirects}회 — "
                                                    "피로·집중 확인 필요"))
        self._support(session, ss, SupportType.REDIRECT, msg, point="off_task")

    # ---------- 단계 결과 ----------
    def _direction(self, session, step: Step, ss: StepState, point: str) -> None:
        err = next((e for e in step.errors if e.id == point), None)
        if err and ss.directions.get(point, 0) == 0:
            q = err.first_question
        elif err:
            q = "앞의 질문을 생각하면서, 제시문의 해당 부분을 다시 읽고 문장을 직접 고쳐 볼까요?"
        else:
            q = "과제가 묻는 것을 다시 확인해 볼까요? 제시문의 어느 부분이 답의 근거가 되는지 살펴보세요."
        ss.directions[point] = ss.directions.get(point, 0) + 1
        self._support(session, ss, SupportType.DIRECTION, q, point)

    def _confirm(self, session, ss: StepState) -> None:
        ss.confirms += 1
        ss.supports.append(SupportRecord(type=SupportType.CONFIRM, text=CONFIRM_QUESTION))
        ss.messages.append(Message(role="tutor", text=CONFIRM_QUESTION, kind="confirm"))
        self.state.log("confirm", session.key, step=ss.step_id)

    def _complete(self, session, step: Step, ss: StepState, lvl: Level, met: list[str]) -> None:
        ss.level = int(lvl)
        ss.status = "done"
        for c in met:
            session.met[c] = max(session.met.get(c, -1), int(lvl))
        msg = step.done_message or "좋아요. 이 과제를 해냈어요."
        if lvl < Level.INDEPENDENT and not step.independent_check:
            msg += " (도움을 받아 해낸 부분은 다음 활동에서 혼자서도 해 볼 거예요.)"
        ss.messages.append(Message(role="tutor", text=msg, kind="done"))
        self.state.log("step_done", session.key, step=step.id, level=int(lvl))
        self._advance(session)

    def _close_not_formed(self, session, step: Step, ss: StepState, met: list[str]) -> None:
        ss.level = int(Level.NOT_FORMED)
        ss.status = "done"
        ss.unresolved = [c.id for c in step.criteria if c.required and c.id not in met]
        for c in ss.unresolved:
            session.met.setdefault(c, int(Level.NOT_FORMED))
        ss.messages.append(Message(role="tutor", kind="done",
                                   text="이 부분은 기록해 두고 다음 활동으로 넘어갈게요. "
                                        "필요하면 짧은 보충 학습에서 다시 다뤄요."))
        self.state.log("step_unresolved", session.key, step=step.id, unresolved=ss.unresolved)
        self._advance(session)

    def _close_unconfirmed(self, session, step: Step, ss: StepState, met: list[str],
                           reason: str, flag: bool) -> None:
        ss.level = None
        ss.status = "done"
        ss.unresolved = [c.id for c in step.criteria if c.required and c.id not in met]
        ss.messages.append(Message(role="tutor", kind="done",
                                   text="여기까지 기록해 둘게요. 이 부분은 다음에 다시 확인해요."))
        if flag:
            self.state.flags.append(Flag(kind="uncertain", source=f"{session.key}/{step.id}",
                                         detail=reason))
        self.state.log("step_unconfirmed", session.key, step=step.id, reason=reason)
        self._advance(session)

    # ---------- 세션 종료와 기준 갱신 ----------
    def _session_levels(self, session: SessionState) -> dict[str, int | None]:
        return {k: v for k, (v, _src) in self._session_levels_src(session).items()}

    def _session_levels_src(self, session: SessionState) -> dict[str, tuple[int | None, str]]:
        """기준별 (수준, 그 수준을 정한 단계 id)."""
        b = self.bundle(session)
        main: dict[str, list[tuple[int, str]]] = defaultdict(list)
        indep: dict[str, list[tuple[int, str]]] = defaultdict(list)
        observed: set[str] = set()
        recheck_only = b.kind == "supplement"
        for step in b.steps:
            ss = session.steps.get(step.id)
            is_check = step.independent_check or step.allow_one_direction
            if recheck_only and not is_check:
                continue                            # 보충 중 직접 연습은 재학습 후 수행 (S1-119)
            for c in step.criteria:
                if not c.required:
                    continue
                for cr in c.evidence_for:
                    observed.add(cr)
                    if is_check:
                        if ss and ss.status == "done" and ss.level is not None and c.id not in ss.unresolved:
                            indep[cr].append((ss.level, step.id))
                    elif c.id in session.met:
                        main[cr].append((session.met[c.id], step.id))
        out: dict[str, tuple[int | None, str]] = {}
        for cr in observed:
            m = min(main[cr]) if main[cr] else None
            i = max(indep[cr]) if indep[cr] else None
            vals = [v for v in (m, i) if v is not None]
            out[cr] = max(vals) if vals else (None, "")
        return out

    def _finish(self, session: SessionState) -> None:
        session.status = "done"
        session.finished_at = now()
        b = self.bundle(session)
        src_map = self._session_levels_src(session)
        session.result = {k: v for k, (v, _s) in src_map.items()}
        for cr, lvl in session.result.items():
            prev = self.state.criteria.get(cr)
            if b.kind == "supplement" and lvl is None:
                continue                        # 재확인 미확인이면 기존 판단 유지 (S1-143)
            if b.kind == "topic" and prev and prev.by == "teacher":
                continue
            # 그 수준을 정한 단계의 최종 답을 근거로 남긴다 (S1-008)
            evidence = session.outputs.get(src_map[cr][1], "")
            src_step = session.steps.get(src_map[cr][1])
            supports = sorted({sp.type.value for sp in src_step.supports}) if src_step else []
            rec = CriterionRecord(level=lvl, source=f"{session.key}/{src_map[cr][1]}",
                                  evidence=evidence[:300], supports=supports, version=session.version)
            self.state.criteria[cr] = rec
            self.state.criteria_history.append((cr, rec))
        if b.kind == "supplement":
            self.state.supplements_done.append(b.id)
            if any(v is None for v in session.result.values()):
                # 수행 미확인 종료 → 같은 보충 반복 대신 교사 검토 (S1-144)
                self.state.flags.append(Flag(kind="not_confirmed", source=b.id,
                                             detail="보충 재확인에서 수행 미확인"))
        self.state.log("session_done", session.key, result=session.result)
        if self.all_topics_done() or b.kind == "supplement":
            self.judge()

    # ---------- 진입 판정 ----------
    def all_topics_done(self) -> bool:
        return all(self.state.sessions.get(t.id) and self.state.sessions[t.id].status == "done"
                   for t in self.pack().topics())

    def criteria_levels(self) -> dict[Criterion, int | None]:
        return {c: (self.state.criteria[c.value].level if c.value in self.state.criteria else None)
                for c in Criterion}

    def judge(self) -> dict:
        major = any(s.major_error for s in self.state.sessions.values())
        res = judge_entry(self.criteria_levels(), major_error=major)
        record = {"decision": res.decision.value, "reasons": res.reasons,
                  "focus": [c.value for c in res.focus],
                  "levels": {c.value: v for c, v in self.criteria_levels().items()}, "ts": now()}
        self.state.entry.append(record)
        self.state.log("entry_judgment", "entry", **record)
        if res.decision == EntryDecision.CONDITIONAL:
            self._recommend_reviews(res.focus)
        if res.decision == EntryDecision.SUPPLEMENT:
            if not self.supplement_options():
                self.state.flags.append(Flag(kind="repeat_difficulty", source="entry",
                                             detail="필요한 보충을 이미 진행함 — 교사 검토 필요"))
        return record

    def latest_entry(self) -> dict | None:
        return self.state.entry[-1] if self.state.entry else None

    def supplement_options(self) -> list[Bundle]:
        """가장 직접적인 결손 1~2개에 대한 보충 경로 (Z-033). 이미 한 경로는 제외 (S1-011)."""
        entry = self.latest_entry()
        if not entry or entry["decision"] != EntryDecision.SUPPLEMENT.value:
            return []
        pack = self.pack()
        seen = {e for s in self.state.sessions.values() for e in s.errors_seen}
        out: list[Bundle] = []
        for cr in entry["focus"][:2]:
            parent = CRITERION_SUPPLEMENT[Criterion(cr)]
            paths = [p for p in pack.supplement_paths(parent)
                     if p.id not in self.state.supplements_done and p.criterion == cr]
            if not paths:
                continue
            hit = [p for p in paths if set(p.trigger_errors) & seen]
            choice = (hit or paths)[0]
            if choice not in out:
                out.append(choice)
        return out

    def _recommend_reviews(self, focus: list[Criterion]) -> None:
        pack = self.pack()
        already = {r.item for r in self.state.reviews}
        for s in self.state.sessions.values():
            b = pack.bundles.get(s.bundle_id)
            if not b:
                continue
            for step in b.steps:
                for e in step.errors:
                    if e.id in s.errors_seen and e.review_item and e.review_item not in already:
                        self.state.reviews.append(ReviewRecord(
                            item=e.review_item, action="recommended", origin=s.key,
                            reason=f"‘{e.name}’ 어려움이 보였어요"))
                        already.add(e.review_item)

    # ---------- 학생 이의·교사 검토 ----------
    def dispute(self, criterion: str, message: str) -> None:
        self.state.flags.append(Flag(kind="dispute", source=criterion, detail=message))
        self.state.log("dispute", criterion, message=message)

    def teacher_set(self, criterion: str, level: int | None, note: str, by: str) -> None:
        rec = CriterionRecord(level=level, source=f"teacher:{by}", by="teacher", note=note,
                              version=active_version())
        self.state.criteria[criterion] = rec
        self.state.criteria_history.append((criterion, rec))
        self.state.log("teacher_set", criterion, level=level, note=note, by=by)
        self.judge()
