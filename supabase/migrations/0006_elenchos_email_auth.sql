-- =========================================================
-- 이메일 가입·로그인 (Supabase Auth 연동) + 학급 코드
-- - 비밀번호 확인·인증 메일·비밀번호 재설정은 Supabase Auth 가 맡는다 (auth.users)
-- - elenchos.accounts 는 역할·표시 이름·동의를 담고, auth_id 로 Auth 사용자와 연결한다
--   (이메일 사용자는 pw_hash = '!' : 로컬 비밀번호 없음)
-- - 학생은 가입 후 교사가 알려 준 학급 코드로 학급에 들어간다
-- =========================================================
alter table elenchos.accounts add column if not exists auth_id uuid unique;
alter table elenchos.accounts add column if not exists email text unique;
alter table elenchos.classes add column if not exists join_code text unique;

create or replace function public.elenchos_account_by_auth(p_key text, p_auth uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  return (select to_jsonb(a) - 'pw_hash' from elenchos.accounts a where a.auth_id = p_auth);
end $$;

create or replace function public.elenchos_account_create_auth(p_key text, p_id text, p_auth uuid, p_email text,
                                                               p_name text, p_consent jsonb) returns void
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  insert into elenchos.accounts (id, login_id, pw_hash, role, display_name, auth_id, email, consent,
                                 must_change_pw, created_by)
  values (p_id, lower(p_email), '!', 'student', coalesce(p_name, ''), p_auth, lower(p_email),
          coalesce(p_consent, '{}'::jsonb), false, 'signup')
  on conflict (auth_id) do nothing;
end $$;

create or replace function public.elenchos_account_set_role(p_key text, p_id text, p_role text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  if p_role not in ('student', 'teacher', 'admin') then
    raise exception 'bad role';
  end if;
  update elenchos.accounts set role = p_role where id = p_id;
end $$;

create or replace function public.elenchos_class_set_code(p_key text, p_id text, p_code text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  update elenchos.classes set join_code = upper(p_code) where id = p_id;
end $$;

create or replace function public.elenchos_class_by_code(p_key text, p_code text) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  return (select jsonb_build_object('id', c.id, 'name', c.name, 'teacher_id', c.teacher_id)
          from elenchos.classes c where c.join_code = upper(p_code));
end $$;

-- 학급 목록에 join_code 를 포함하도록 다시 정의
create or replace function public.elenchos_class_list(p_key text, p_teacher text) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  return coalesce((select jsonb_agg(jsonb_build_object(
            'id', c.id, 'name', c.name, 'teacher_id', c.teacher_id, 'pack_id', c.pack_id, 'created_at', c.created_at,
            'join_code', c.join_code,
            'students', coalesce((select jsonb_agg(jsonb_build_object('id', a.id, 'login_id', a.login_id,
                                   'email', a.email, 'display_name', a.display_name, 'active', a.active,
                                   'last_login', a.last_login, 'must_change_pw', a.must_change_pw) order by a.login_id)
                                  from elenchos.class_members m join elenchos.accounts a on a.id = m.student_id
                                  where m.class_id = c.id), '[]'::jsonb)) order by c.created_at)
                   from elenchos.classes c where p_teacher is null or c.teacher_id = p_teacher), '[]'::jsonb);
end $$;

-- 학생이 속한 학급
create or replace function public.elenchos_classes_of_student(p_key text, p_student text) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  perform elenchos.check_key(p_key);
  return coalesce((select jsonb_agg(jsonb_build_object('id', c.id, 'name', c.name))
                   from elenchos.class_members m join elenchos.classes c on c.id = m.class_id
                   where m.student_id = p_student), '[]'::jsonb);
end $$;

do $$
declare f text;
begin
  foreach f in array array[
    'elenchos_account_by_auth(text, uuid)', 'elenchos_account_create_auth(text, text, uuid, text, text, jsonb)',
    'elenchos_account_set_role(text, text, text)', 'elenchos_class_set_code(text, text, text)',
    'elenchos_class_by_code(text, text)', 'elenchos_class_list(text, text)',
    'elenchos_classes_of_student(text, text)']
  loop
    execute format('revoke all on function public.%s from public, authenticated', f);
    execute format('grant execute on function public.%s to anon', f);
  end loop;
end $$;
