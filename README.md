# 📝 논술랩 · 논술 기초 다지기

「논술학습 기초다지기 요구사항 정의서」에 따라 만든 **본격 논술 학습 진입 준비 과정**입니다.
학생은 다섯 학습 주제를 한 번씩 수행하고, 필요할 때만 짧은 집중 보충을 받은 뒤 **진입 준비 판정**을 받습니다.
점수를 더하지 않고, 실제로 쓴 답과 받은 도움을 기준으로 다섯 기준을 기록합니다.

| 영역 | 기술 |
|---|---|
| UI | Streamlit (`st.navigation` 역할별 메뉴) |
| DB / 인증 | Supabase (PostgreSQL + Auth + RLS) |
| AI | Claude / OpenAI — **답변 분석만** 담당 (판정·반복 상한·보충은 시스템 정책) |
| 콘텐츠 | `content/v1/*.yaml` (버전 고정) |

📘 **화면과 함께 보는 전체 소개: [docs/INTRODUCTION.md](docs/INTRODUCTION.md)**

요구사항별 반영 위치와 미구현 항목은 **[docs/requirements_traceability.md](docs/requirements_traceability.md)**에 정리했습니다.

## 🧭 학습 흐름

```
학습 주제 1~5 (각 1회)                     필요할 때만               판정
① 읽고 한 문장으로 잡기       ─┐
② 주장과 이유 연결하기         │
③ 두 글 비교와 추론 점검(1·2차) ├─▶ 진입 준비 판정 ─▶ 집중 보충(S1~S5, 경로당 1회) ─▶ 재확인 ─▶ 재판정
④ 내 주장을 세우고 시험하기    │      (기준 ①~⑤)                                     │
⑤ 짧게 쓰고 고치기(400자)     ─┘                                                     └▶ 본격 6단계 (준비 중)
```

학생은 튜터와 **문답 창**에서 주고받습니다. 과제와 무관한 말·정답 요구·질문은 먼저 구분해 즉시 과제로 되돌립니다.

한 활동 안의 교수 순서 (Z-014): **스스로 시도 → 진단 → 방향 질문(같은 판단점 최대 2회) → 설명 → 별도 사례 시범 → 기록 후 이동**.
지원을 받은 수행은 독립 수행으로 기록하지 않습니다.

| 수준 | 뜻 |
|---|---|
| 3 독립 수행 | 지원 없이 수행 |
| 2 최소 지원 후 수행 | 정답 없는 방향 질문·과제 안내 뒤 수행 |
| 1 집중 지원 후 수행 | 설명·시범 뒤 수행 |
| 0 미형성 | 설명·시범 후에도 수행 미확인 |
| 미확인 | 증거 부족. 오답이 아님 |

진입 판정 (Z-028): 다섯 기준 모두 2 이상 + ①·② 포함 셋 이상이 3 → **진입 가능** / 모두 2 이상이거나 ③~⑤ 중 하나만 1 → **조건부 진입** / ①·② 중 1 이하·0 존재·③~⑤ 중 둘 이상 1 → **집중 보충 후 재확인** / 미확인 → **판정 보류**.

## 📁 폴더 구조

```
.
├── app.py                        # 진입점: 테마 + 역할별 메뉴
├── views/
│   ├── login.py                  # 로그인 / 회원가입
│   ├── home.py                   # 학생 홈: 오늘의 목표, 다섯 학습 주제 진행
│   ├── lesson.py                 # 수업 화면 (제시문 · 과제 · 튜터 대화 · 도움 요청)
│   ├── result.py                 # 진입 준비 결과 · 보충 안내 · 이의 신청
│   ├── review.py                 # 선택 복습 (1-1 ~ 5-7)
│   ├── records.py                # 교사: 기준별 판정·근거·지원 이력·검토 요청·판정 수정
│   └── content_admin.py          # 교사: 자료 버전·내부 출처·사용 중지
├── content/
│   ├── active.yaml               # 새 학습에 쓰는 활성 버전
│   └── v1/
│       ├── excerpts.yaml         # 제시문 (학생에겐 (가) 라벨과 본문만, 출처는 내부)
│       ├── review_items.yaml     # 복습 항목 38개
│       └── bundles/              # L1~L5 학습 주제, S1~S5 보충 경로 23개
├── src/
│   ├── learning/                 # ★ 공통 실행 틀
│   │   ├── content.py            # 콘텐츠 스키마·로더·검증, 글자 수 규칙
│   │   ├── engine.py             # 교수 정책 엔진
│   │   ├── entry.py              # 진입 준비 판정표
│   │   ├── levels.py             # 수준·지원 공통 기록 스키마
│   │   ├── analyzer.py           # AI 분석기 / 데모 분석기
│   │   └── state.py              # 학습 기록 모델
│   ├── ai/                       # Claude·OpenAI 제공자
│   ├── db/                       # Supabase 클라이언트, 학습 기록 저장소(데모/Supabase)
│   ├── services/                 # 인증, 학습 서비스
│   ├── core/config.py            # 환경 설정
│   └── ui/                       # 디자인 토큰·CSS, 공통 컴포넌트
├── supabase/migrations/          # 0001 인증·프로필, 0002 학습 기록
├── tests/                        # 판정표·엔진 정책·로그인 테스트
├── static/fonts/                 # Pretendard (SIL OFL)
└── docs/                         # 요구사항 반영 현황, 실행 화면
```

## 🧪 테스트 로그인 (키 없이 바로 체험)

| 아이디 | 비밀번호 |
|---|---|
| `test` | `testpoc` |

- Supabase·AI 키 없이 학생 화면과 교사 화면을 모두 볼 수 있습니다 (`admin` 권한).
- 기록은 브라우저 세션에만 저장되고, 로그아웃하거나 새로고침하면 초기화됩니다.
- AI 키가 없으면 **데모 분석기**가 콘텐츠에 적힌 키워드 단서로 판정합니다. 시연용이라 타당한 다른 표현을 놓칠 수 있습니다. 키를 넣으면 실제 AI가 같은 판단 기준으로 분석합니다.
- `APP_ENV=production` 또는 `ENABLE_TEST_LOGIN=false`이면 자동 비활성화됩니다.

| 수업 (방향 질문) | 진단 결과 | 교사 학습 기록 |
|---|---|---|
| ![수업](docs/screenshots/desktop_03_direction.png) | ![결과](docs/screenshots/B_02_result_supplement.png) | ![기록](docs/screenshots/desktop_08_records.png) |

> ⚠️ `content/v1`의 제시문은 모두 **시범용 신규 설계문**입니다. 실제 저작의 인용이 아니며, 운영 전에 승인된 발췌문으로 교체해야 합니다.

## 🎨 디자인 시스템

모든 스타일 값은 `src/ui/theme.py`의 `TOKENS`에 모여 있습니다 (`.streamlit/config.toml`도 같은 값 사용).

| 역할 | 값 | 용도 |
|---|---|---|
| Navy 900 / 800 | `#0F1C3F` / `#14254F` | 제목, 히어로·브랜드 패널 |
| Primary | `#2B50D6` | 주요 버튼, 선택 상태, 진행바 |
| Primary 50 | `#EEF2FE` | 선택된 메뉴·탭 배경, 포커스 링 |
| Background | `#F6F7FB` | 앱 배경 (저채도 쿨그레이, 장시간 작업용) |
| Surface | `#FFFFFF` | 카드, 입력창 |
| Text / Muted | `#1B2233` / `#7A8499` | 본문 / 보조 텍스트 |
| Success · Warning · Danger | `#0F9D74` · `#C98112` · `#D64545` | 완료·잠시 멈춤·분량 초과 |

- **글꼴:** Pretendard Variable (자체 호스팅). 제시문은 줄간격 1.95로 장문 가독성 강화
- **모양:** 입력·버튼 10px, 카드 18px 둥근 모서리, 3단계 그림자(`shadow-sm/shadow/shadow-lg`)
- **반응형:** 본문 최대 1120px · 900px/640px 구간에서 여백·글자 크기 축소, 통계 카드 2열, 컬럼 세로 쌓기

## 🚀 시작하기

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env            # 키 입력
```

1. [Supabase](https://supabase.com)에서 프로젝트 생성 → **SQL Editor**에서 `supabase/migrations/0001_init.sql`, `0002_learning.sql` 순서로 실행
2. **Project Settings → API**에서 URL / anon key를 `.env`에 입력
3. Claude 또는 OpenAI API 키를 `.env`에 입력하고 `AI_PROVIDER` 선택
4. 실행:
   ```bash
   streamlit run app.py
   ```
5. 교사 계정은 가입 후 SQL Editor에서 역할 변경:
   ```sql
   update public.profiles set role = 'teacher' where email = 'teacher@example.com';
   ```

## 🧪 LLM 품질 관리 (Ragas)

답변 분석 AI를 정답 라벨 42건(골든셋)과 Ragas(`Faithfulness`, `DiscreteMetric` judge)로 평가하고, 기준 미달이면 실패 처리합니다. 결과는 교사 화면 **AI 품질**에서 확인합니다.

```bash
pip install -r requirements-eval.txt
python -m evals.run_eval --analyzer llm --ragas   # 실제 AI + Ragas (키 필요)
python -m evals.run_eval --analyzer demo          # 키 없이 회귀 기준선
```

자세한 내용: [docs/llm_quality.md](docs/llm_quality.md)

## 🗂 콘텐츠 수정

제시문·판단 기준·첫 대응 질문·설명·시범은 `content/v1/` YAML에서 고칩니다. 앱은 시작할 때 참조 무결성을 검사합니다(없는 제시문·복습 항목, 독립 확인에 시범 자료 사용 등). 진행 중인 학습을 보존하려면 내용을 크게 바꿀 때 `content/v2/`를 새로 만들고 `content/active.yaml`의 버전을 바꾸세요.

## ✅ 테스트 / 린트

```bash
pytest
ruff check .
```

## 🔐 보안 메모
- `.env`, `.streamlit/secrets.toml`은 `.gitignore`에 포함되어 커밋되지 않습니다.
- 모든 테이블에 RLS가 켜져 있어 학생은 본인 기록만, 교사는 전체를 조회할 수 있습니다.
- 현재 학생 기록은 학생 권한으로 저장되므로, 운영 전에는 판정 쓰기를 서버 측 함수로 분리해야 합니다 (docs 참고).
- `SUPABASE_SERVICE_ROLE_KEY`는 RLS를 우회하므로 클라이언트 코드에서 사용하지 마세요.
