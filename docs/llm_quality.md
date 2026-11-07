# LLM 품질 관리 (Ragas)

답변 분석 AI가 요구사항 정의서의 판단 원칙을 지키는지 **정답 라벨(골든셋)**과 **Ragas** 지표로 측정하고,
기준(품질 게이트)을 못 넘으면 배포 전에 걸러냅니다.

## 무엇을 재나요

AI의 역할은 학생 답 분석(충족 기준·대표 오류·불확실 여부)으로 제한되어 있습니다(Z-049). 그래서 두 가지를 봅니다.

| 구분 | 지표 | 방법 | 요구사항 |
|---|---|---|---|
| 판정이 맞는가 | 판정 정확도 | 골든셋 라벨과 비교 | Z-017 |
| | **다른 표현 답 탈락률** | 예시와 다르지만 타당한 답을 탈락시킨 비율 | P-013, L3-010 |
| | **반대 의견 답 탈락률** | 필자에 반대하지만 정확히 읽은 답을 탈락시킨 비율 (0 이어야 함) | L1-016, L2-024 |
| | 미충족 답 통과율 | 기준 미달 답을 통과시킨 비율 | Z-008 |
| | 대표 오류 정확도 | 오류 유형을 맞혀야 알맞은 첫 질문이 나감 | L1-013, L2-023 |
| 발화를 구분하는가 | 엉뚱한 답·질문 감지율 | 무관한 말·정답 요구·질문을 답과 구분해 즉시 과제로 되돌리는지 | Z-015, Z-030 |
| | 답을 무관한 말로 오인한 비율 | 학생의 진짜 답을 무시하지 않는지 (0 에 가까워야 함) | Z-017 |
| 근거가 믿을 만한가 | **Ragas Faithfulness** | 판단 근거(rationale)를 원자 문장으로 쪼개 제시문·학생 답·판단 기준에 비추어 뒷받침 비율 계산 | P-004, P-022 |
| | **Ragas 근거-판정 일치** | `DiscreteMetric`(pass/fail) LLM judge: 근거가 판정을 뒷받침하는가, 의미로 판단했는가, 반대 의견을 감점하지 않았는가, 제시문 밖 근거를 쓰지 않았는가 | P-013, Z-049 |

judge 모델은 분석기와 **다른 모델**을 권장합니다(기본 `claude-opus-5-5`, `EVAL_JUDGE_MODEL`로 변경).

## 구성

```
evals/
├── datasets/analyzer_golden.yaml   # 골든셋 51건 (답 42 + 엉뚱한 답·질문·정답 요구 9) (사례마다 근거 요구사항 ref)
├── golden.py                       # 실행 + 결정적 지표
├── ragas_judge.py                  # Ragas Faithfulness · DiscreteMetric judge
├── report.py                       # 품질 게이트 판정, JSON·Markdown 보고서
├── run_eval.py                     # CLI
├── thresholds.yaml                 # 기준 (llm: 운영 / demo: 회귀 기준선)
└── reports/                        # 결과 (baseline_demo.json 만 저장소에 보관)
```

- 교사·운영자 화면 **AI 품질**에서 보고서를 볼 수 있습니다 (지표·기준·라벨과 다른 사례·Ragas 판정 이유).
- `.github/workflows/llm-eval.yml`
  - PR (콘텐츠·엔진·평가 변경 시): 테스트 + 데모 분석기 회귀 기준선 — 키 불필요
  - 수동 실행·매주: 실제 AI 분석기 + Ragas — 저장소 Secret `ANTHROPIC_API_KEY`(또는 `OPENAI_API_KEY`) 필요, 보고서를 아티팩트로 저장

## 실행

```bash
pip install -r requirements-eval.txt
```
```bash
python -m evals.run_eval --analyzer llm --ragas
```
```bash
python -m evals.run_eval --analyzer llm --ragas --tag valid_alternative --limit 10
```
```bash
python -m evals.run_eval --analyzer demo
```

기준 미달이면 종료 코드 1, 골든셋이 콘텐츠와 맞지 않으면 2.

## 운영 절차

1. **콘텐츠·프롬프트를 바꿀 때** — PR 에서 데모 회귀가 자동 실행됩니다. 분석 프롬프트(`src/learning/analyzer.py`)나 판단 기준을 바꿨다면 `--analyzer llm --ragas` 를 수동 실행해 기준 통과를 확인합니다.
2. **모델을 바꿀 때** (`ANTHROPIC_MODEL`) — 반드시 LLM 평가를 돌리고 보고서를 비교합니다.
3. **골든셋 늘리기** — 교사가 학습 기록에서 판정을 수정한 사례, 학생 이의 신청 사례, AI 품질 화면에서 라벨과 달랐던 사례를 `analyzer_golden.yaml`에 추가합니다. 사례마다 근거 요구사항(ref)을 적습니다.
4. **기준 조정** — `thresholds.yaml` 은 초기값입니다. 시범 운영에서 교사 판정과의 일치도를 보고 조정합니다.

## 현재 상태

| 항목 | 상태 |
|---|---|
| 데모 분석기 기준선 | 판정 정확도 0.905, 다른 표현 답 탈락률 0.375 — 키워드 방식의 한계를 수치로 확인 (운영에는 실제 AI 필요) |
| 평가 체계가 찾은 콘텐츠 결함 | L4 입론 단서에 ‘-야 한다’ 형태 누락 → 수정 |
| Ragas 호출 경로 | 가짜 judge 로 Faithfulness·DiscreteMetric 전 과정 테스트 (`tests/test_evals.py`) |
| 실제 AI 분석기 + Ragas 측정 | **아직 미실행** — API 키 등록 후 첫 측정 필요 |

## 앞으로

- 원문 검색(RAG, P-002)을 구현하면 Ragas 의 `ContextPrecision`·`ContextRecall`·`Faithfulness` 로 **발췌문 검색 품질**과 **해석 문장의 원문 근거성**을 같은 체계에서 측정합니다.
- 운영 기록(학습 기록의 분석 근거)을 표본 추출해 라벨 없이 Faithfulness 를 주기적으로 측정하는 모니터링.
