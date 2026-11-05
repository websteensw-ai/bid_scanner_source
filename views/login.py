import streamlit as st

from src.core.config import get_settings
from src.services import auth_service
from src.ui.components import card, html

settings = get_settings()

brand, form = st.columns([1.05, 1], gap="large", vertical_alignment="center")

with brand:
    html("""
    <div class="nx-brand">
      <div class="nx-eyebrow">논술 기초 다지기</div>
      <h1>읽고, 잇고,<br>내 글로 세우기.</h1>
      <p>다섯 가지 학습 주제로 본격 논술 학습을 준비해요.
         먼저 스스로 해 보고, 필요한 만큼만 도움을 받아요.</p>
      <div class="nx-feature"><div class="i">📝</div>
        <div><b>먼저 스스로 해 보기</b><span>답을 미리 알려 주지 않고, 내가 쓴 답에 맞춰 질문해요</span></div></div>
      <div class="nx-feature"><div class="i">🎯</div>
        <div><b>필요한 만큼만 도움</b><span>질문 → 설명 → 시범 순으로, 받은 도움은 따로 기록해요</span></div></div>
      <div class="nx-feature"><div class="i">✏️</div>
        <div><b>점수가 아닌 성장 기록</b><span>지금 할 수 있는 것과 다음 학습을 알려 줘요</span></div></div>
    </div>""")

with form, card("login"):
    html('<div class="nx-label">시작하기</div>'
         '<h2 style="margin:0 0 .3rem;font-size:1.6rem">다시 오신 걸 환영해요 👋</h2>'
         '<p style="color:var(--text-muted);margin:0 0 1.2rem">계정으로 로그인하고 '
         '오늘의 논술을 이어 써 보세요.</p>')
    if settings.test_login_enabled:
        html(f'<div class="nx-demo">🧪 <b>테스트 계정</b>으로 바로 체험할 수 있어요<br>'
             f'아이디 <code>{settings.test_login_id}</code> &nbsp;비밀번호 '
             f'<code>{settings.test_login_password}</code></div>')

    login_tab, signup_tab = st.tabs(["로그인", "회원가입"])
    with login_tab, st.form("login", border=False):
        login_id = st.text_input("이메일 또는 아이디", placeholder="name@school.ac.kr")
        pw = st.text_input("비밀번호", type="password", placeholder="비밀번호 입력")
        if st.form_submit_button("로그인", type="primary", width="stretch"):
            try:
                auth_service.sign_in(login_id, pw)
                st.rerun()
            except Exception as e:
                st.error(f"로그인에 실패했어요. 아이디와 비밀번호를 확인해 주세요. ({e})")

    with signup_tab, st.form("signup", border=False):
        name = st.text_input("이름", placeholder="홍길동")
        email = st.text_input("이메일", key="su_email", placeholder="name@school.ac.kr")
        pw2 = st.text_input("비밀번호", type="password", key="su_pw", placeholder="6자 이상")
        if st.form_submit_button("가입하기", type="primary", width="stretch"):
            try:
                auth_service.sign_up(email, pw2, name)
                st.success("가입이 완료됐어요! 이메일 인증 후 로그인해 주세요.")
            except Exception as e:
                st.error(f"가입에 실패했어요: {e}")
