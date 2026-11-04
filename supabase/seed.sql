-- 개발용 샘플 데이터. 교사 계정은 가입 후 아래처럼 역할을 변경하세요.
-- update public.profiles set role = 'teacher' where email = 'teacher@example.com';

insert into public.assignments (title, prompt, min_chars, max_chars) values
('AI와 인간의 창의성',
 '생성형 AI가 만든 작품을 인간의 창작물과 동등하게 볼 수 있는가? 자신의 입장을 정하고 근거를 들어 논술하시오.',
 800, 1600);
