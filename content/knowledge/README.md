# 지식자산 · 사고원형 DB 입력 안내

지식자산 기본계획 ⅩⅤ장을 따르는 네 가지 핵심 DB의 입력 형식이에요. 지금 들어 있는 자료는 형식을 검증하기 위한 **샘플**이고, 원문 전문은 넣지 않았어요.

| DB | 파일 | 단위 |
|---|---|---|
| ① 원천 지식자산 | `sources.yaml` | 평론·칼럼·저술 1편 |
| ② 사고원형 | `archetypes.yaml` | 반복 적용되는 보편적 질문 1개 |
| ③ 논제·제시문 | `topics.yaml` | 사고원형을 특정 상황에 적용한 학습 문제 1개 |
| ④ 학습자 성장 | 학생 기록(LearnerState.think) | 학생별 역량 프로파일·학습 이력 |

역량 목록은 `competencies.yaml`, 초기 진단 과제와 추천 가중치는 `diagnostic.yaml`에 있어요. 11개 역량 전체 목록을 받으면 `competencies.yaml`만 바꾸면 돼요.

## 50편 시범 DB 구성 (24절)

철학 10 · 정치·법 10 · 인간관계·윤리 10 · 리더십·역사적 선택 10 · 과학·사회·문명 10. 각 자료의 `pilot_group`에 이 다섯 이름 중 하나를 적어요.

## 원천 자료 1편 (sources.yaml)

```yaml
- id: SRC-0004                 # 고유 번호
  title: 『국가』 평론
  source_type: 고전평론         # 고전평론·명저평론·고전칼럼 등
  asset_type: concept          # concept 개념·명제형 / choice 인물·선택·결과형 / policy 정책·사회문제형 / history 역사적 사례형 / literature 문학·인간이해형
  author: {original: 플라톤, commentary: 평설 저자}
  work: 『국가』
  era: 고대                    # 고대·중세·근대·현대
  region: 그리스
  fields: [철학, 정치]
  persons: [플라톤, 트라시마코스]
  public: summary              # full 전문 제공 / summary 요약만 / none 비공개
  copyright: own               # own 자체 저작 / public_domain / restricted
  pilot_group: 철학
  concepts: [정의, 강자의 이익]
  claim: 핵심 명제
  counter_claim: 대립 명제
  hidden_premise: 숨은 전제
  counterexamples: [주요 반례]
  conflicts: ["정의 vs 이익"]   # 반드시 'A vs B' 형식 (관계 태그)
  universal_question: 정의는 강자의 이익에 불과한가?
  tags: [권력, 도덕]
  review: {status: draft, reviewer: ""}   # draft → approved (전문가 검수 후)
```

## 사고원형 (archetypes.yaml)

```yaml
- id: ARC-006
  question: 정의는 강자의 이익에 불과한가?
  sources: [SRC-0004]
  conflicts: ["정의 vs 이익"]
  concepts: [정의, 권력]
  positions: [입장 1, 입장 2]
  counterexamples: [반례]
  situations: [적용 가능한 상황]
  abilities: [define, counter]   # competencies.yaml 의 id
  level_range: [2, 5]
```

## 논제 (topics.yaml)

```yaml
- id: TOP-008
  archetypes: [ARC-006]          # 2개 이상이면 교차 논제 (cross: true)
  prompt: 실제 학생에게 줄 논제
  form: dilemma                  # dilemma 딜레마 / comparison 비교 / policy 정책 / concept 개념
  level: 3                       # 논제 사고 난이도 1~5 (자료 난이도와 따로)
  mode: B                        # A 독서 선행 / B 사고 선행 / C 탐구 발견
  abilities: [define, counter]
  expected_turns: "6~10"
  rebuttal: mid                  # low / mid / high
  review: draft                  # approved 인 논제만 학생에게 추천
```

## 작업 순서 (23절)

1. 교사 화면 **지식자산 DB → AI 1차 구조화**에 원문을 붙여 넣어 사고구조 초안을 만들어요.
2. 전문가가 핵심 명제·대립 명제·사고원형·가치충돌·연결을 검수해 YAML에 옮겨요.
3. `python -m src.think.kb`로 형식과 참조를 검사하고 50편 구축 현황을 확인해요.
