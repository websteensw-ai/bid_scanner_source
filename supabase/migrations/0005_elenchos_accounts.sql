-- =========================================================
-- 계정·학급 (6단계 MVP 가이드 12·13·14장, 결정 1: 교사가 학급 단위로 학생 계정 발급)
-- - 학생 실명·연락처는 받지 않는다. 교사가 발급한 아이디와 표시 이름만 저장한다.
-- - 비밀번호는 앱 서버에서 PBKDF2-SHA256(무작위 salt)으로 해시한 값만 저장한다.
-- - 학습 기록 learner_states.id = accounts.id (계정별 기록)
-- - 테이블은 노출하지 않고, 서버 비밀키를 확인하는 함수로만 접근한다.
-- =========================================================
create table if not exists elenchos.accounts (
  id             text primary key,                         -- u-xxxxxxxx
  login_id       text not null unique,
  pw_hash        text not null,
  role           text not null check (role in ('student', 'teacher', 'admin')),
  display_name   text not null default '',
  active         boolean not null default true,
  must_change_pw boolean not null default true,
  consent        jsonb not null default '{}'::jsonb,
  failed_logins  int not null default 0,
  locked_until   timestamptz,
  created_by     text,
  created_at     timestamptz not null default now(),
  last_login     timestamptz
);
create table if not exists elenchos.classes (
  id         text primary key,                             -- c-xxxxxx
  name       text not null,
  teacher_id text not null references elenchos.accounts(id),
  pack_id    text not null default 'BASIC-Q1',
  created_at timestamptz not null default now()
);
create table if not exists elenchos.class_members (
  class_id   text not null references elenchos.classes(id) on delete cascade,
  student_id text not null references elenchos.accounts(id) on delete cascade,
  added_at   timestamptz not null default now(),
  primary key (class_id, student_id)
);
create table if not exists elenchos.audit_log (
  id     bigint generated always as identity primary key,
  who    text not null,
  action text not null,
  target text not null default '',
  at     timestamptz not null default now()
);
alter table elenchos.accounts enable row level security;
alter table elenchos.classes enable row level security;
alter table elenchos.class_members enable row level security;
alter table elenchos.audit_log enable row level security;

-- ---------- 계정 ----------
create or replace function public.elenchos_account_by_login(p_key text, p_login text) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  return (select to_jsonb(a) from elenchos.accounts a where a.login_id = lower(p_login));
end $$;

create or replace function public.elenchos_account_get(p_key text, p_id text) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  return (select to_jsonb(a) - 'pw_hash' from elenchos.accounts a where a.id = p_id);
end $$;

create or replace function public.elenchos_account_create(p_key text, p_id text, p_login text, p_hash text,
                                                          p_role text, p_name text, p_by text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  insert into elenchos.accounts (id, login_id, pw_hash, role, display_name, created_by)
  values (p_id, lower(p_login), p_hash, p_role, coalesce(p_name, ''), p_by);
end $$;

create or replace function public.elenchos_account_update(p_key text, p_id text, p_patch jsonb) returns void
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  update elenchos.accounts set
    pw_hash        = coalesce(p_patch->>'pw_hash', pw_hash),
    must_change_pw = coalesce((p_patch->>'must_change_pw')::boolean, must_change_pw),
    active         = coalesce((p_patch->>'active')::boolean, active),
    display_name   = coalesce(p_patch->>'display_name', display_name),
    consent        = coalesce(p_patch->'consent', consent),
    failed_logins  = coalesce((p_patch->>'failed_logins')::int, failed_logins),
    locked_until   = case when p_patch ? 'locked_until' then (p_patch->>'locked_until')::timestamptz else locked_until end,
    last_login     = case when p_patch ? 'last_login' then now() else last_login end
  where id = p_id;
end $$;

create or replace function public.elenchos_account_list(p_key text, p_role text) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  return coalesce((select jsonb_agg(to_jsonb(a) - 'pw_hash' order by a.display_name, a.login_id)
                   from elenchos.accounts a where p_role is null or a.role = p_role), '[]'::jsonb);
end $$;

-- ---------- 학급 ----------
create or replace function public.elenchos_class_create(p_key text, p_id text, p_name text, p_teacher text,
                                                        p_pack text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  insert into elenchos.classes (id, name, teacher_id, pack_id) values (p_id, p_name, p_teacher, coalesce(p_pack, 'BASIC-Q1'));
end $$;

create or replace function public.elenchos_class_list(p_key text, p_teacher text) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  return coalesce((select jsonb_agg(jsonb_build_object(
            'id', c.id, 'name', c.name, 'teacher_id', c.teacher_id, 'pack_id', c.pack_id, 'created_at', c.created_at,
            'students', coalesce((select jsonb_agg(jsonb_build_object('id', a.id, 'login_id', a.login_id,
                                   'display_name', a.display_name, 'active', a.active, 'last_login', a.last_login,
                                   'must_change_pw', a.must_change_pw) order by a.login_id)
                                  from elenchos.class_members m join elenchos.accounts a on a.id = m.student_id
                                  where m.class_id = c.id), '[]'::jsonb)) order by c.created_at)
                   from elenchos.classes c where p_teacher is null or c.teacher_id = p_teacher), '[]'::jsonb);
end $$;

create or replace function public.elenchos_class_add_member(p_key text, p_class text, p_student text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  insert into elenchos.class_members (class_id, student_id) values (p_class, p_student) on conflict do nothing;
end $$;

-- ---------- 감사 로그 ----------
create or replace function public.elenchos_audit(p_key text, p_who text, p_action text, p_target text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  insert into elenchos.audit_log (who, action, target) values (p_who, p_action, coalesce(p_target, ''));
end $$;

do $$
declare f text;
begin
  foreach f in array array[
    'elenchos_account_by_login(text, text)', 'elenchos_account_get(text, text)',
    'elenchos_account_create(text, text, text, text, text, text, text)', 'elenchos_account_update(text, text, jsonb)',
    'elenchos_account_list(text, text)', 'elenchos_class_create(text, text, text, text, text)',
    'elenchos_class_list(text, text)', 'elenchos_class_add_member(text, text, text)',
    'elenchos_audit(text, text, text, text)']
  loop
    execute format('revoke all on function public.%s from public, authenticated', f);
    execute format('grant execute on function public.%s to anon', f);
  end loop;
end $$;
