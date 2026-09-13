# 공공 입찰공고 수집·매칭 파이프라인 (bid-scanner)

기업마당, IRIS, K-Startup, 나라장터의 공고를 수집하고 HWP/HWPX/PDF 첨부파일(과업지시서/RFP)을 분석하여, 회사의 실제 사업 영역과의 연관도를 LLM으로 평가·선별하는 파이썬 파이프라인입니다. CLI(고정 프로필)와 웹앱(회사 홈페이지 URL 기반 동적 프로필) 두 가지 방식으로 사용할 수 있습니다.

## 1. 디렉터리 구조
- `extractors/doc_parser.py`: HWP (olefile), HWPX (zip/xml), PDF (pypdf) 텍스트 추출 모듈
- `collectors/`: 기업마당·IRIS·K-Startup·나라장터 수집기 (`keywords.py`에 공용 기본 키워드)
- `analyzers/llm_evaluator.py`: LLM 기반 시맨틱 연관도 판별 및 항목 추출 모듈
- `analyzers/site_profiler.py`: 회사 웹사이트를 분석해 사업 영역 요약·제외기준·키워드를 자동 생성
- `exporters/excel_exporter.py`: 서식화된 Excel 리포트 내보내기 모듈
- `pipeline.py`: 수집→파싱→LLM평가 공용 파이프라인 (CLI/웹앱이 공유)
- `main.py`: CLI 실행 진입점 (기본 AX 프로필 사용)
- `app.py`, `templates/`: 웹앱 (URL 입력 → 자동 분석 → 결과 테이블/엑셀 다운로드)

## 2. 설치 및 환경설정
```bash
pip install -r requirements.txt
cp .env.example .env
# .env 파일에 GEMINI_API_KEY 입력
# 나라장터를 쓰려면 G2B_SERVICE_KEY(data.go.kr 발급)도 입력
# 웹앱의 회원가입/리포트 저장을 쓰려면 아래 4번 Supabase 설정도 진행
```

## 3. 실행 방법

### CLI (고정 프로필)
```bash
python main.py --days 7 --min-score 70
```

### 웹앱 (회사 URL 기반 동적 매칭 + 로그인/리포트 저장)
```bash
python app.py
# http://localhost:5000 접속 → 회원가입/로그인 후 회사 홈페이지 주소 입력
```
웹앱은 이제 로그인해야 분석을 실행할 수 있고, 분석이 끝나면 결과가 Supabase `bid_scanner_reports` 테이블에 자동 저장됩니다. `/reports`에서 본인이 실행한 리포트 이력을 확인하고 엑셀을 다시 내려받을 수 있습니다.

## 4. Supabase 연동 설정 (회원가입 + 리포트 저장)

이 프로젝트는 Supabase Auth(이메일/비밀번호)로 회원가입·로그인을 처리하고, 분석 결과를 `bid_scanner_reports` 테이블에 저장합니다. 서버는 사용자의 로그인 토큰으로만 DB에 접근하므로 **service_role 키는 사용하지 않습니다** (분실/유출 위험이 큰 키라 이 구조에선 아예 필요 없게 설계했습니다).

### 4-1. API 키 확인
Supabase 대시보드 → 해당 프로젝트(`xslldyhouksjpcgdurtj`) → **Project Settings → API** 에서 아래 값을 확인해 `.env`에 넣습니다.
- `SUPABASE_URL` → `https://xslldyhouksjpcgdurtj.supabase.co` (이미 `.env`/`.env.example`에 채워둠)
- `SUPABASE_ANON_KEY` → "anon public" 키 값을 복사해서 `.env`의 `SUPABASE_ANON_KEY`에 붙여넣기 (이 키는 채워져 있지 않으니 반드시 직접 입력해야 합니다)

### 4-2. 이메일 인증 방식 확인
Supabase 대시보드 → **Authentication → Providers → Email** 이 활성화되어 있는지 확인합니다.
- "Confirm email"이 켜져 있으면 회원가입 후 이메일 인증 링크를 클릭해야 로그인할 수 있습니다.
- 로컬 테스트를 빠르게 하고 싶다면 이 옵션을 꺼서 가입 즉시 로그인되도록 할 수 있습니다 (운영 배포 시에는 켜두는 것을 권장합니다).

### 4-3. `bid_scanner_reports` 테이블 생성
Supabase 대시보드 → **SQL Editor**에서 아래 스크립트를 실행합니다.

```sql
create table if not exists public.bid_scanner_reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  url text,
  days int,
  min_score int,
  business_profile jsonb,
  results jsonb,
  result_count int default 0,
  created_at timestamptz not null default now()
);

create index if not exists bid_scanner_reports_user_id_created_at_idx
  on public.bid_scanner_reports (user_id, created_at desc);

alter table public.bid_scanner_reports enable row level security;

create policy "Users can view own bid_scanner_reports"
  on public.bid_scanner_reports for select
  using (auth.uid() = user_id);

create policy "Users can insert own bid_scanner_reports"
  on public.bid_scanner_reports for insert
  with check (auth.uid() = user_id);
```

RLS(Row Level Security) 정책 덕분에 각 사용자는 본인이 만든 리포트만 조회/저장할 수 있고, 서버는 anon 키 + 사용자 access_token만으로 안전하게 이 규칙을 그대로 적용받습니다.

### 4-4. 동작 확인
```bash
python app.py
```
1. `http://localhost:5000/signup`에서 이메일/비밀번호/회사명/담당자명/연락처/회사 홈페이지 주소를 입력하고 약관에 동의해 회원가입
2. (이메일 인증을 켜둔 경우) 메일함에서 인증 링크 클릭 후 `/login`으로 로그인
3. 로그인하면 메인(`/`)이 분석 화면으로 바뀌고, 가입 때 등록한 홈페이지 주소가 자동으로 채워져 있음을 확인 → 분석 실행 → 완료 후 `/reports`에서 저장된 이력과 엑셀 다운로드 확인

## 5. 회원 정보 및 약관 동의
- 가입 시 이메일/비밀번호 외에 **회사명, 담당자명, 담당자 연락처, 회사 홈페이지 주소**를 함께 수집합니다. 모두 Supabase 사용자 메타데이터(`user_metadata`)에 저장됩니다.
- **AI 서비스 이용약관 동의**와 **개인정보 수집·이용 동의**는 필수이며, 동의하지 않으면 가입이 진행되지 않습니다. **마케팅 정보 수신 동의**는 선택 항목입니다. 동의 여부와 동의 시각(`consent_at`)도 함께 저장됩니다.
- 약관/방침 페이지는 [templates/terms.html](templates/terms.html), [templates/privacy.html](templates/privacy.html)에 초안으로 작성되어 있습니다. **실제 서비스 오픈 전 반드시 법률 검토를 받아 내용을 확정해주세요.**

## 6. 회사 홈페이지 주소 자동 재사용
가입 시 입력한 회사 홈페이지 주소는 Supabase 사용자 메타데이터(`user_metadata.company_url`)에 저장되어, 로그인할 때마다 메인 화면 입력란에 자동으로 채워집니다. 이후 다른 주소로 분석을 실행하면 그 값이 새로운 기본값으로 갱신되어 다음 로그인부터 반영됩니다.

## 7. 랜딩 페이지
로그인하지 않은 상태로 `/`에 접속하면 서비스 소개 랜딩 페이지([templates/landing.html](templates/landing.html))가 보이고, 로그인한 상태에서는 바로 분석 화면으로 연결됩니다. 랜딩 페이지의 "20여 개 국가", "100여 개 기업 이용 중" 문구는 요청하신 카피를 그대로 반영한 것으로, 실제 서비스 범위·이용 현황과 다르다면 문구를 조정해주세요 (현재 파이프라인은 기업마당·IRIS·K-Startup·나라장터 등 국내 소스만 수집합니다).
