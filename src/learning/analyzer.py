"""학생 답변 분석기 (Z-049: AI 는 답변 분석과 설명·질문 생성만 담당).

분석기는 '어떤 기준을 충족했는가, 어떤 오류가 보이는가'만 돌려준다.
다음 행동(질문·설명·시범·이동·판정)은 engine 의 정책이 결정한다.

- LLMAnalyzer: Claude/OpenAI 로 분석 (승인된 판단 기준 안에서만)
- DemoAnalyzer: API 키 없이 시연하기 위한 단서(signals) 기반 분석. 실제 평가에 쓰지 않는다.
"""
import json
import re

from pydantic import BaseModel, Field

from src.learning.content import Excerpt, Step
from src.learning.intent import ANSWER, ANSWER_REQUEST, OFF_TASK, QUESTION, classify, relevance


class Diagnosis(BaseModel):
    intent: str = "answer"          # answer / question / answer_request / off_task (intent.py)
    asked_word: str | None = None   # 낱말 뜻 질문일 때 그 낱말
    met: list[str] = Field(default_factory=list)
    primary_error: str | None = None
    concept_gap: bool = False       # 과제·개념 자체를 이해하지 못함
    uncertain: bool = False         # 판정이 불확실 (확인 질문 필요)
    rationale: str = ""             # 내부 기록용


class Analyzer:
    name = "base"

    def analyze(self, step: Step, answer: str, evidence: str, choice: str | None,
                excerpts: list[Excerpt], context: dict[str, str]) -> Diagnosis:
        raise NotImplementedError


_GIVE_UP = re.compile(r"(모르겠|모름|잘 몰라|어려워요|못 하겠|모르겟)")


def _match(groups: list[list[str]], text: str) -> bool:
    return bool(groups) and all(any(k in text for k in g) for g in groups)


class DemoAnalyzer(Analyzer):
    """키워드 단서 기반 시연용 분석기. 실제 운영 평가에는 LLMAnalyzer 를 쓴다."""
    name = "demo"

    def analyze(self, step, answer, evidence, choice, excerpts, context):
        text = f"{answer}\n{evidence}".strip()
        if not answer.strip() or _GIVE_UP.search(answer) and len(answer) < 40:
            return Diagnosis(concept_gap=True, rationale="(데모) 과제 이해 어려움 표현")
        if not choice and relevance(answer, step, excerpts, context) == 0:
            return Diagnosis(intent=OFF_TASK, rationale="(데모) 과제·제시문과 겹치는 내용이 없음")
        met = []
        for c in step.criteria:
            if c.expected_choice is not None:
                ok = choice == c.expected_choice
                if c.signals:
                    ok = ok and _match(c.signals, text)
                if ok:
                    met.append(c.id)
            elif (not c.signals or _match(c.signals, text)) and not any(a in answer for a in c.absent):
                met.append(c.id)
        error = next((e.id for e in step.errors
                      if (e.on_choice and choice == e.on_choice) or _match(e.signals, text)), None)
        required = [c.id for c in step.criteria if c.required]
        if error is None and not all(r in met for r in required):
            unmet = [c for c in step.criteria if c.required and c.id not in met]
            # 미충족 기준과 연결된 오류를 대표 오류로 사용
            error = next((e.id for e in step.errors if e.id in {u.id for u in unmet}), None)
            if error is None and step.errors:
                error = step.errors[0].id
        uncertain = len(answer.strip()) < 8 and not met
        return Diagnosis(met=met, primary_error=None if all(r in met for r in required) else error,
                         uncertain=uncertain, rationale="(데모) 단서 기반 판정")


_SYSTEM = """당신은 논술 기초 과정의 답변 분석기입니다. 교사가 승인한 판단 기준과 오류 유형만 사용해
학생 답변을 분석하고 JSON 으로만 답합니다. 수업 진행·정답 공개·판정은 하지 않습니다.

규칙
- 예시 문구와 다르더라도 타당한 다른 표현·해석은 충족으로 인정합니다 (특정 문구 일치로 판정하지 않음).
- 제시문만으로 알 수 없는 내용을 거짓으로 판정하지 않습니다.
- 필자 견해에 반대하는 것은 오류가 아닙니다. 독해 기준만 봅니다.
- 판단 근거가 부족하거나 답이 애매하면 uncertain=true 로 둡니다.
- 학생이 과제의 뜻이나 개념 자체를 모른다는 신호가 분명하면 concept_gap=true.
- primary_error 는 실제로 보인 가장 중요한 오류 하나의 id (없으면 null).
- intent: 학생 입력이 과제에 대한 답이면 "answer", 과제·제시문과 무관한 말(잡담·장난·딴 이야기)이면
  "off_task", 튜터에게 묻는 질문이면 "question", 정답을 알려 달라는 요구면 "answer_request".
  틀리거나 부족한 답, 논제에서 벗어났지만 과제에 답하려 한 글은 "answer" 입니다.

출력 형식: {"intent": "answer", "met": [기준 id...], "primary_error": "오류 id 또는 null",
            "concept_gap": false, "uncertain": false, "rationale": "판단 근거 한두 문장"}"""


class LLMAnalyzer(Analyzer):
    name = "llm"

    def __init__(self, provider):
        self.provider = provider
        self.name = f"{provider.name}:{provider.model}"

    def analyze(self, step, answer, evidence, choice, excerpts, context):
        passages = "\n\n".join(f"{e.label}\n" + "\n".join(e.paragraphs) for e in excerpts)
        crit = "\n".join(f"- {c.id}: {c.desc}" + (f" (정답 선택지: {c.expected_choice})"
                                                  if c.expected_choice else "")
                         for c in step.criteria)
        errs = "\n".join(f"- {e.id}: {e.name}" for e in step.errors)
        prev = "\n".join(f"- {k}: {v}" for k, v in context.items())
        user = (f"<제시문>\n{passages}\n</제시문>\n"
                + (f"<학습용_해석_문장>{step.sentence}</학습용_해석_문장>\n" if step.sentence else "")
                + f"<과제>{step.prompt}</과제>\n<판단_기준>\n{crit}\n</판단_기준>\n"
                f"<오류_유형>\n{errs}\n</오류_유형>\n"
                + (f"<앞선_산출물>\n{prev}\n</앞선_산출물>\n" if prev else "")
                + (f"<선택>{choice}</선택>\n" if choice else "")
                + f"<학생_답>\n{answer}\n</학생_답>\n<근거_표시>{evidence}</근거_표시>")
        raw = self.provider._complete(_SYSTEM, user)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return Diagnosis(uncertain=True, rationale="분석 응답 형식 오류")
        d = Diagnosis.model_validate(json.loads(m.group(0)))
        valid_c = {c.id for c in step.criteria}
        valid_e = {e.id for e in step.errors}
        d.met = [x for x in d.met if x in valid_c]
        if d.primary_error not in valid_e:
            d.primary_error = None
        if d.intent not in (ANSWER, QUESTION, ANSWER_REQUEST, OFF_TASK):
            d.intent = ANSWER
        return d


def diagnose(analyzer: Analyzer, step: Step, answer: str, evidence: str, choice: str | None,
             excerpts: list[Excerpt], context: dict[str, str]) -> Diagnosis:
    """분명한 비(非)답변은 규칙으로 즉시 가리고, 나머지만 분석기에 맡긴다 (엔진·평가 공용)."""
    if not choice:
        intent, word = classify(answer, step)
        if intent != ANSWER:
            return Diagnosis(intent=intent, asked_word=word, rationale=f"(규칙) 의도 분류: {intent}")
    return analyzer.analyze(step, answer, evidence, choice, excerpts, context)


def get_analyzer(demo: bool) -> Analyzer:
    from src.ai.factory import get_provider
    from src.core.config import get_settings

    s = get_settings()
    key = s.anthropic_api_key if s.ai_provider == "claude" else s.openai_api_key
    if demo and not key:
        return DemoAnalyzer()
    return LLMAnalyzer(get_provider(s))
