-- =========================================================
-- 논술랩(elenchos.kr) 학습 기록 저장소 — Supabase 'AI counselor' 프로젝트에 적용됨 (2026-11-15)
-- 기존 public 테이블과 분리된 전용 스키마. 테이블은 API 로 노출하지 않고,
-- 서버 비밀키(elenchos.config 의 api_key = Vercel 환경변수 ELENCHOS_DB_KEY)를 확인하는 함수로만 접근한다.
-- 판정·기록 쓰기는 서버(Vercel 함수)에서만 일어나므로 학생이 자기 기록을 고칠 수 없다.
--
-- 비밀키 등록 (값은 저장소에 커밋하지 말 것):
--   insert into elenchos.config (name, value) values ('api_key', '<무작위 64자>')
--   on conflict (name) do update set value = excluded.value;
-- =========================================================
create schema if not exists elenchos;
revoke all on schema elenchos from public, anon, authenticated;

create table if not exists elenchos.learner_states (
  id           text primary key,
  state        jsonb not null,
  is_demo      boolean not null default true,
  display_name text not null default '',
  updated_at   timestamptz not null default now()
);
create table if not exists elenchos.content_status (
  item_id    text primary key,
  status     text not null check (status in ('approved', 'suspended')),
  note       text not null default '',
  updated_by text,
  updated_at timestamptz not null default now()
);
create table if not exists elenchos.config (name text primary key, value text not null);
alter table elenchos.learner_states enable row level security;
alter table elenchos.content_status enable row level security;
alter table elenchos.config enable row level security;

create or replace function elenchos.check_key(p_key text) returns void
language plpgsql security definer set search_path = '' as $$
declare v text;
begin
  select value into v from elenchos.config where name = 'api_key';
  if v is null or p_key is null or p_key <> v then
    raise exception 'unauthorized' using errcode = '28000';
  end if;
end $$;

create or replace function public.elenchos_get_state(p_key text, p_id text) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  return (select state from elenchos.learner_states where id = p_id);
end $$;

create or replace function public.elenchos_put_state(p_key text, p_id text, p_state jsonb,
                                                     p_is_demo boolean, p_name text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  insert into elenchos.learner_states (id, state, is_demo, display_name, updated_at)
  values (p_id, p_state, p_is_demo, coalesce(p_name, ''), now())
  on conflict (id) do update
    set state = excluded.state, is_demo = excluded.is_demo,
        display_name = case when excluded.display_name = '' then elenchos.learner_states.display_name
                            else excluded.display_name end,
        updated_at = now();
end $$;

create or replace function public.elenchos_list_states(p_key text, p_include_demo boolean)
returns jsonb language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  return coalesce((select jsonb_agg(jsonb_build_object('id', id, 'display_name', display_name,
                                                       'is_demo', is_demo, 'updated_at', updated_at)
                                    order by updated_at desc)
                   from elenchos.learner_states where p_include_demo or not is_demo), '[]'::jsonb);
end $$;

create or replace function public.elenchos_get_suspended(p_key text) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  return coalesce((select jsonb_object_agg(item_id, note) from elenchos.content_status
                   where status = 'suspended'), '{}'::jsonb);
end $$;

create or replace function public.elenchos_set_status(p_key text, p_item text, p_status text,
                                                      p_note text, p_by text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  insert into elenchos.content_status (item_id, status, note, updated_by, updated_at)
  values (p_item, p_status, coalesce(p_note, ''), p_by, now())
  on conflict (item_id) do update
    set status = excluded.status, note = excluded.note, updated_by = excluded.updated_by, updated_at = now();
end $$;

revoke all on function elenchos.check_key(text) from public, anon, authenticated;
revoke all on function public.elenchos_get_state(text, text) from public;
revoke all on function public.elenchos_put_state(text, text, jsonb, boolean, text) from public;
revoke all on function public.elenchos_list_states(text, boolean) from public;
revoke all on function public.elenchos_get_suspended(text) from public;
revoke all on function public.elenchos_set_status(text, text, text, text, text) from public;
grant execute on function public.elenchos_get_state(text, text) to anon;
grant execute on function public.elenchos_put_state(text, text, jsonb, boolean, text) to anon;
grant execute on function public.elenchos_list_states(text, boolean) to anon;
grant execute on function public.elenchos_get_suspended(text) to anon;
grant execute on function public.elenchos_set_status(text, text, text, text, text) to anon;
