-- =========================================================
-- 기초 다지기 학습 기록 (요구사항 정의서 Z-025·Z-048·P-014)
-- 0001 의 과제·논술·100점 피드백 테이블은 총점 기반 평가(Z-029 위반)라
-- 학습 엔진으로 대체되었다. 기존 데이터가 없다면 아래 DROP 을 실행해도 된다.
-- =========================================================

-- drop table if exists public.feedbacks;
-- drop table if exists public.essays;
-- drop table if exists public.assignments;

-- 학생별 학습 상태 (LearnerState JSON: 세션·최초/수정 답·지원 이력·기준별 판정·검토 요청·이벤트)
create table public.learner_states (
  student_id uuid primary key references public.profiles(id) on delete cascade,
  state      jsonb not null,
  updated_at timestamptz not null default now()
);
create trigger learner_states_updated_at before update on public.learner_states
  for each row execute function public.set_updated_at();

-- 자료 사용 중지·재개 (P-014). item_id 는 묶음 id(L1, S1-가) 또는 제시문 id
create table public.content_status (
  item_id    text primary key,
  status     text not null check (status in ('approved', 'suspended')),
  note       text not null default '',
  updated_by text,
  updated_at timestamptz not null default now()
);
create trigger content_status_updated_at before update on public.content_status
  for each row execute function public.set_updated_at();

alter table public.learner_states enable row level security;
alter table public.content_status enable row level security;

-- 학생: 본인 기록만 읽고 쓴다. 교사: 전체 조회·수정 (판정 검토·수정, Z-048)
create policy "learner_states_select" on public.learner_states for select
  using (student_id = auth.uid() or public.is_teacher());
create policy "learner_states_insert" on public.learner_states for insert
  with check (student_id = auth.uid() or public.is_teacher());
create policy "learner_states_update" on public.learner_states for update
  using (student_id = auth.uid() or public.is_teacher());

-- 자료 상태: 로그인 사용자 조회, 교사만 변경
create policy "content_status_select" on public.content_status for select
  using (auth.role() = 'authenticated');
create policy "content_status_write" on public.content_status for all
  using (public.is_teacher()) with check (public.is_teacher());

-- 참고: 학생이 자기 상태 JSON 을 직접 고칠 수 있으므로, 운영 단계에서는
-- 판정(criteria·entry)을 서버 측 함수(Edge Function)에서만 쓰도록 분리하는 것을 권장한다.
