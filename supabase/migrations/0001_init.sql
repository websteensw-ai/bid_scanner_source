-- =========================================================
-- AI 논술 첨삭 프로그램 초기 스키마
-- Supabase 대시보드 > SQL Editor 에 붙여넣어 실행하거나
-- `supabase db push` 로 적용하세요.
-- =========================================================

-- ---------- ENUM ----------
create type public.user_role    as enum ('student', 'teacher', 'admin');
create type public.essay_status as enum ('draft', 'submitted', 'reviewed');

-- ---------- 공통: updated_at 자동 갱신 ----------
create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;

-- ---------- profiles (auth.users 1:1) ----------
create table public.profiles (
  id         uuid primary key references auth.users(id) on delete cascade,
  email      text not null,
  full_name  text,
  role       public.user_role not null default 'student',
  created_at timestamptz not null default now()
);

-- 회원가입 시 profiles 자동 생성
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email, full_name)
  values (new.id, new.email, new.raw_user_meta_data->>'full_name');
  return new;
end; $$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- 현재 사용자가 교사/관리자인지 (RLS 재귀 방지용 security definer)
create or replace function public.is_teacher() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles
                 where id = auth.uid() and role in ('teacher', 'admin'));
$$;

-- ---------- assignments (과제/논제) ----------
create table public.assignments (
  id         uuid primary key default gen_random_uuid(),
  title      text not null,
  prompt     text not null,
  min_chars  int  not null default 800,
  max_chars  int  not null default 1600,
  due_at     timestamptz,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  check (min_chars <= max_chars)
);

-- ---------- essays (학생 답안) ----------
create table public.essays (
  id            uuid primary key default gen_random_uuid(),
  student_id    uuid not null references public.profiles(id) on delete cascade,
  assignment_id uuid not null references public.assignments(id) on delete cascade,
  content       text not null default '',
  status        public.essay_status not null default 'draft',
  submitted_at  timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (student_id, assignment_id)
);
create index on public.essays (assignment_id);
create trigger essays_updated_at before update on public.essays
  for each row execute function public.set_updated_at();

-- ---------- feedbacks (AI 첨삭 결과) ----------
create table public.feedbacks (
  id           uuid primary key default gen_random_uuid(),
  essay_id     uuid not null references public.essays(id) on delete cascade,
  total_score  int  not null check (total_score between 0 and 100),
  result       jsonb not null,          -- FeedbackResult 전체
  provider     text not null,           -- claude | openai
  model        text not null,
  created_at   timestamptz not null default now()
);
create index on public.feedbacks (essay_id);

-- =========================================================
-- Row Level Security
-- =========================================================
alter table public.profiles    enable row level security;
alter table public.assignments enable row level security;
alter table public.essays      enable row level security;
alter table public.feedbacks   enable row level security;

-- profiles: 본인 조회, 교사는 전체 조회
create policy "profiles_select" on public.profiles for select
  using (id = auth.uid() or public.is_teacher());

-- assignments: 로그인 사용자 조회, 교사만 생성/수정/삭제
create policy "assignments_select" on public.assignments for select
  using (auth.role() = 'authenticated');
create policy "assignments_write" on public.assignments for all
  using (public.is_teacher()) with check (public.is_teacher());

-- essays: 학생 본인 CRUD(초안 상태에서만 수정), 교사 전체 조회
create policy "essays_select" on public.essays for select
  using (student_id = auth.uid() or public.is_teacher());
create policy "essays_insert" on public.essays for insert
  with check (student_id = auth.uid());
create policy "essays_update" on public.essays for update
  using (student_id = auth.uid() and status = 'draft');

-- feedbacks: 본인 답안 피드백 조회 + 본인 답안에 대한 생성, 교사 전체
create policy "feedbacks_select" on public.feedbacks for select
  using (public.is_teacher() or exists (
    select 1 from public.essays e where e.id = essay_id and e.student_id = auth.uid()));
create policy "feedbacks_insert" on public.feedbacks for insert
  with check (public.is_teacher() or exists (
    select 1 from public.essays e where e.id = essay_id and e.student_id = auth.uid()));

-- 피드백 저장 시 답안 상태를 'reviewed' 로 전환 (학생 RLS 우회)
create or replace function public.mark_essay_reviewed() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  update public.essays set status = 'reviewed' where id = new.essay_id;
  return new;
end; $$;

create trigger feedbacks_mark_reviewed
  after insert on public.feedbacks
  for each row execute function public.mark_essay_reviewed();
