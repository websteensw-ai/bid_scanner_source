-- =========================================================
-- 지도·시스템 의견 저장소 (6단계 MVP 가이드 9·14장)
-- 학습 기록(learner_states)과 분리된 테이블. 익명 제출이면 계정 ID 를 저장하지 않고,
-- 제출 시각도 날짜 단위로만 남긴다. 접근은 서버 비밀키를 확인하는 함수로만.
-- =========================================================
create table if not exists elenchos.feedback (
  id         bigint generated always as identity primary key,
  kind       text not null,                       -- reflection_type1 등
  answers    jsonb not null,
  named      boolean not null default false,
  user_id    text,                                -- 실명 제출일 때만
  day        date not null default current_date,  -- 정확한 시각 대신 날짜
  status     text not null default 'received',
  constraint feedback_anon check (named or user_id is null)
);
alter table elenchos.feedback enable row level security;

create or replace function public.elenchos_add_feedback(p_key text, p_kind text, p_answers jsonb, p_user text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  insert into elenchos.feedback (kind, answers, named, user_id)
  values (p_kind, p_answers, p_user is not null, p_user);
end $$;

create or replace function public.elenchos_list_feedback(p_key text) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  return coalesce((select jsonb_agg(jsonb_build_object('kind', kind, 'answers', answers, 'named', named,
                                                       'user_id', user_id, 'day', day, 'status', status)
                                    order by id desc) from elenchos.feedback), '[]'::jsonb);
end $$;

revoke all on function public.elenchos_add_feedback(text, text, jsonb, text) from public;
revoke all on function public.elenchos_list_feedback(text) from public;
grant execute on function public.elenchos_add_feedback(text, text, jsonb, text) to anon;
grant execute on function public.elenchos_list_feedback(text) to anon;
