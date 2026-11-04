import streamlit as st

from src.core.config import get_settings
from src.services import auth_service
from src.ui.components import card, html

settings = get_settings()

brand, form = st.columns([1.05, 1], gap="large", vertical_alignment="center")

with brand:
    html("""
    <div class="nx-brand">
      <div class="nx-eyebrow">AI 논술 첨삭 플랫폼</div>
      <h1>생각을 글로,<br>글을 실력으로.</h1>
      <p>논제 분석부터 문장 첨삭까지, 제출 즉시 루브릭 기반의
         구체적인 피드백을 받아보세요.</p>
      <div class="nx-feature"><div class="i">📝</div>
        <div><b>집중하기 좋은 작성 환경</b><span>분량 가이드와 작성 팁을 옆에 두고 써요</span></div></div>
      <div class="nx-feature"><div class="i">🎯</div>
        <div><b>5개 항목 루브릭 평가</b><span>논제 이해 · 논증력 · 구성 · 표현 · 창의성</span></div></div>
      <div class="nx-feature"><div class="i">✏️</div>
        <div><b>문장 단위 첨삭</b><span>무엇을 왜 고쳐야 하는지 바로 확인해요</span></div></div>
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
        if st.form_submit_button("로그인", type="primary", use_container_width=True):
            try:
                auth_service.sign_in(login_id, pw)
                st.rerun()
            except Exception as e:
                st.error(f"로그인에 실패했어요. 아이디와 비밀번호를 확인해 주세요. ({e})")

    with signup_tab, st.form("signup", border=False):
        name = st.text_input("이름", placeholder="홍길동")
        email = st.text_input("이메일", key="su_email", placeholder="name@school.ac.kr")
        pw2 = st.text_input("비밀번호", type="password", key="su_pw", placeholder="6자 이상")
        if st.form_submit_button("가입하기", type="primary", use_container_width=True):
            try:
                auth_service.sign_up(email, pw2, name)
                st.success("가입이 완료됐어요! 이메일 인증 후 로그인해 주세요.")
            except Exception as e:
                st.error(f"가입에 실패했어요: {e}")
