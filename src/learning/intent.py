"""학생 발화의 의도 분류 (답 / 질문 / 정답 요구 / 과제와 무관).

엔진은 분석기를 부르기 전에 이 규칙으로 '분명한 경우'를 먼저 가려 즉시 응답한다.
- 규칙은 정밀도 우선: 애매하면 'answer' 로 두고 분석기(AI)에 맡긴다.
- 과제와 무관한지 여부를 내용 겹침으로 추정하는 relevance() 는 데모 분석기에서만 쓴다
  (실제 AI 분석기는 의미로 판단해 intent 를 돌려준다).
"""
import re

from src.learning.content import Excerpt, Step

ANSWER = "answer"
QUESTION = "question"
ANSWER_REQUEST = "answer_request"
OFF_TASK = "off_task"

_ANSWER_REQUEST = re.compile(
    r"(정답|모범\s*답|답안?)\s*(이|을|좀|만)?\s*(뭐|알려|가르쳐|보여|줘|주세요|주실|말해)"
    r"|답\s*(좀|만)\s*(알려|줘|주세요)|대신\s*(써|해)\s*(줘|주세요)|그냥\s*답")
_QUESTION = re.compile(
    r"(무슨\s*뜻|뜻이\s*뭐|뜻이\s*뭔|뜻\s*알려|뭐예요|뭔가요|뭐에요|뭐죠|뭐야\s*\??$"
    r"|어떻게\s*(해야|하면|해요|써요|쓰면|써야|시작)|뭘\s*(해야|하라는|쓰라는|쓰면)|무엇을\s*(해야|쓰라는)"
    r"|왜\s*해야|이해가\s*안|어떤\s*걸\s*(써|쓰))")
_LAUGH_OR_MASH = re.compile(r"^[\sㄱ-ㅎㅏ-ㅣ!?.~ㅋㅎㅠㅜ^_\-]+$|^(asdf|qwer|zxcv|[a-z]{1,3})+$|^(.)\1{3,}$",
                            re.IGNORECASE)
_OFF_TASK_PHRASE = re.compile(
    r"(배고|졸려|졸리|심심|게임|유튜브|점심|급식\s*뭐|집에\s*가|놀고\s*싶|하기\s*싫|재미없|귀찮|몰라\s*ㅋ)")

# 겹침 판단에서 뺄 흔한 말 (내용과 무관)
_STOP = {"이거", "그거", "저거", "그냥", "진짜", "너무", "근데", "그리고", "저는", "제가", "나는", "내가",
         "이건", "그건", "무슨", "하고", "싶어", "싶다", "있어", "없어", "해요", "합니다", "같아", "같은",
         "언제", "어디", "누가", "정말", "완전", "약간", "조금", "많이", "아니", "그래", "네요", "어요",
         "선생", "튜터", "오늘", "지금", "이제", "우리", "여기", "거기"}


def classify(text: str, step: Step) -> tuple[str, str | None]:
    """(의도, 물어본 낱말). 확신할 수 없으면 ('answer', None)."""
    t = text.strip()
    if not t:
        return ANSWER, None
    if _LAUGH_OR_MASH.match(t):
        return OFF_TASK, None
    if _ANSWER_REQUEST.search(t):
        return ANSWER_REQUEST, None
    if _QUESTION.search(t) and len(t) <= 60:
        word = next((w for w in step.vocab if w in t), None)
        return QUESTION, word
    if _OFF_TASK_PHRASE.search(t) and len(t) <= 40:
        return OFF_TASK, None
    return ANSWER, None


def _stems(text: str) -> set[str]:
    out = set()
    for tok in re.findall(r"[가-힣]+", text):
        if tok in _STOP or tok[:2] in _STOP:
            continue
        out.add(tok[:2] if len(tok) >= 2 else tok)
    return out


def relevance(text: str, step: Step, excerpts: list[Excerpt], context: dict[str, str]) -> int:
    """답과 과제(제시문·과제 문구·해석 문장·선택지·앞 산출물)의 내용 겹침 수. 0 이면 무관 가능성."""
    ref = " ".join([step.prompt, step.title, step.sentence or "", " ".join(step.choices),
                    *(p for e in excerpts for p in e.paragraphs), *context.values(),
                    *(c.desc for c in step.criteria)])
    return sum(1 for s in _stems(text) if s in ref)
