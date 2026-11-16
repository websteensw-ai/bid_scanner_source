"""이메일 인증 코드(OTP) 로그인·처음 시작 정보·학급 코드 참여 테스트 (Supabase Auth 대신 MemoryAuth)."""
import re

import pytest
from fastapi.testclient import TestClient

from src.core.passwords import hash_pw
from web import store as store_mod
from web.main import app
from web.supa_auth import MemoryAuth

CONSENT = {"c_service": "1", "c_ai": "1", "c_teacher": "1", "age14": "1"}


@pytest.fixture()
def env(monkeypatch):
    mem = store_mod.MemoryStore()
    auth = MemoryAuth()
    monkeypatch.setattr("web.main.get_store", lambda: mem)
    monkeypatch.setattr("web.email_auth.get_auth", lambda: auth)
    return mem, auth


def last_code(auth, email):
    return [m for m in auth.outbox if m["to"] == email and m["type"] == "otp"][-1]["token"]


def otp_login(c, auth, email="stu@example.com"):
    r = c.post("/login/code", data={"email": email})
    assert "인증 코드" in r.text and email in r.text
    return c.post("/login/verify", data={"code": last_code(auth, email)}, follow_redirects=False)


def test_bad_email_and_wrong_code_limits(env):
    mem, auth = env
    c = TestClient(app)
    assert "형식" in c.post("/login/code", data={"email": "nope"}).text
    c.post("/login/code", data={"email": "stu@example.com"})
    for _ in range(5):
        r = c.post("/login/verify", data={"code": "000000"})
        assert r.status_code == 400 and "맞지 않거나" in r.text
    r = c.post("/login/verify", data={"code": last_code(auth, "stu@example.com")})
    assert r.status_code == 429 and "새 코드" in r.text
    assert "초 뒤에" in c.post("/login/code/resend").text          # 재전송 대기
    assert c.post("/login/verify", data={"code": "1"}, follow_redirects=False).status_code == 429
    assert TestClient(app).post("/login/verify", data={"code": "123456"}, follow_redirects=False).headers["location"] == "/login"


def test_first_login_profile_then_join_and_teacher_view(env):
    mem, auth = env
    c = TestClient(app)
    r = otp_login(c, auth)
    assert r.status_code == 303 and r.headers["location"] == "/welcome"
    acc = next(iter(mem.accounts.values()))
    assert acc["email"] == "stu@example.com" and acc["role"] == "student" and acc["pw_hash"] == "!"
    # 시작 정보 전에는 다른 화면으로 못 감
    assert c.get("/mvp", follow_redirects=False).headers["location"] == "/welcome"
    assert "필수 동의" in c.post("/welcome", data={"display_name": "별칭", "c_service": "1", "age14": "1"}).text
    assert "14세" in c.post("/welcome", data={"display_name": "별칭", **{**CONSENT, "age14": ""}}).text
    r = c.post("/welcome", data={"display_name": "별칭", **CONSENT}, follow_redirects=False)
    assert r.headers["location"] == "/mvp/join"
    assert acc["display_name"] == "별칭" and acc["consent"]["ai"] and not acc["consent"]["research"]
    # 다른 기기에서 다시 코드 로그인 → 시작 정보는 다시 묻지 않음
    other = TestClient(app)
    assert otp_login(other, auth).headers["location"] == "/"
    assert "학급에 참여하지 않았어요" in other.get("/mvp").text
    assert len(mem.accounts) == 1                                  # 같은 계정
    # 이메일 계정은 비밀번호 화면이 없음
    assert other.get("/account/password", follow_redirects=False).headers["location"] == "/"
    # 교사: 코드로 가입 → 관리자가 교사 권한 → 학급·코드 → 학생 참여 → 열람
    mem.account_create("u-admin", "admin", hash_pw("admin-pass-1"), "admin", "관리자", "seed")
    mem.account_update("u-admin", {"must_change_pw": False})
    t = TestClient(app)
    otp_login(t, auth, "teach@example.com")
    t.post("/welcome", data={"display_name": "김 선생님", **CONSENT})
    tid = next(a["id"] for a in mem.accounts.values() if a.get("email") == "teach@example.com")
    assert t.get("/teacher/accounts").status_code == 403
    admin = TestClient(app)
    admin.post("/login", data={"login_id": "admin", "password": "admin-pass-1"})
    assert "사용자 역할" in admin.get("/teacher/accounts").text
    admin.post("/admin/role", data={"account_id": tid, "role": "teacher"})
    t = TestClient(app)
    otp_login(t, auth, "teach@example.com")
    t.post("/teacher/accounts/class", data={"name": "논술 B반"})
    code = mem.class_list(tid)[0]["join_code"]
    assert re.fullmatch(r"[A-Z2-9]{6}", code) and code in t.get("/teacher/accounts").text
    sid = acc["id"]
    assert t.get(f"/teacher/mvp/student/{sid}").status_code == 403
    assert "찾지 못했어요" in other.post("/mvp/join", data={"code": "ZZZZZZ"}).text
    assert "참여했어요" in other.post("/mvp/join", data={"code": code.lower()}).text
    other.post("/mvp/start")
    assert t.get(f"/teacher/mvp/student/{sid}").status_code == 200
    assert sid in mem.states


def test_deactivated_email_account_cannot_login(env):
    mem, auth = env
    c = TestClient(app)
    otp_login(c, auth)
    aid = next(iter(mem.accounts))
    mem.account_update(aid, {"active": False})
    r = otp_login(TestClient(app), auth)
    assert r.status_code == 403 and "사용이 중지된" in r.text


def test_link_style_mail_still_works(env):
    mem, auth = env
    auth.send_otp("link@example.com")
    uid = next(u["id"] for u in auth.users.values() if u["email"] == "link@example.com")
    token = auth._token(uid)
    c = TestClient(app)
    assert c.get("/auth/callback").status_code == 200
    r = c.post("/auth/session", json={"access_token": token, "type": "magiclink"})
    assert r.json() == {"ok": True, "next": "/welcome"}
    bad = TestClient(app).post("/auth/session", json={"access_token": "forged"})
    assert bad.status_code == 400
