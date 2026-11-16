"""이메일 가입·인증·로그인·비밀번호 재설정·학급 코드 참여 테스트 (Supabase Auth 대신 MemoryAuth)."""
import re

import pytest
from fastapi.testclient import TestClient

from web import store as store_mod
from web.main import app
from web.supa_auth import MemoryAuth

CONSENT = {"c_service": "1", "c_ai": "1", "c_teacher": "1", "age14": "1"}


@pytest.fixture()
def env(monkeypatch):
    mem = store_mod.MemoryStore()
    auth = MemoryAuth(confirm_required=True)
    monkeypatch.setattr("web.main.get_store", lambda: mem)
    monkeypatch.setattr("web.email_auth.get_auth", lambda: auth)
    return mem, auth


def signup(c, email="stu@example.com", pw="good-pass-1", name="별칭", **extra):
    data = {"email": email, "password": pw, "confirm": pw, "display_name": name, **CONSENT, **extra}
    return c.post("/signup", data=data)


def confirm(c, auth, kind="signup"):
    mail = [m for m in auth.outbox if m["type"] == kind][-1]
    assert mail["redirect_to"].endswith("/auth/callback")
    assert c.get("/auth/callback").status_code == 200          # 조각(#token)을 읽는 페이지
    return c.post("/auth/session", json={"access_token": mail["token"], "type": kind})


def test_signup_validation(env):
    c = TestClient(app)
    assert "형식" in signup(c, email="nope").text
    assert "서로 달라요" in c.post("/signup", data={"email": "a@b.co", "password": "good-pass-1",
                                                  "confirm": "x", "display_name": "a", **CONSENT}).text
    r = c.post("/signup", data={"email": "a@b.co", "password": "good-pass-1", "confirm": "good-pass-1",
                                "display_name": "a", "c_service": "1", "age14": "1"})
    assert "필수 동의" in r.text
    r = signup(c, age14="")
    assert "14세" in r.text


def test_signup_confirm_login_join_and_teacher_view(env):
    mem, auth = env
    c = TestClient(app)
    r = signup(c)
    assert "메일을 확인해 주세요" in r.text
    acc = next(iter(mem.accounts.values()))
    assert acc["email"] == "stu@example.com" and acc["role"] == "student" and acc["pw_hash"] == "!"
    assert acc["consent"]["ai"] and acc["consent"]["age14"] and not acc["consent"]["research"]
    # 인증 전 로그인 → 안내
    r = c.post("/login", data={"login_id": "stu@example.com", "password": "good-pass-1"})
    assert r.status_code == 401 and "인증" in r.text
    # 메일 링크 → 로그인됨 → 학급 참여 화면
    r = confirm(c, auth)
    assert r.json() == {"ok": True, "next": "/mvp/join"}
    assert "학급 코드" in c.get("/mvp/join").text
    # 다른 기기에서 이메일 로그인
    other = TestClient(app)
    r = other.post("/login", data={"login_id": "STU@example.com", "password": "good-pass-1"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert "학급에 참여하지 않았어요" in other.get("/mvp").text
    # 같은 이메일로 다시 가입 → 거절
    assert "이미 가입한" in signup(TestClient(app)).text
    # 교사: 관리자가 권한 부여 → 학급 + 코드 → 학생 참여 → 교사가 기록 열람
    mem.account_create("u-admin", "admin", __import__("src.core.passwords", fromlist=["x"]).hash_pw("admin-pass-1"),
                       "admin", "관리자", "seed")
    mem.account_update("u-admin", {"must_change_pw": False})
    signup(TestClient(app), email="teach@example.com", name="김 선생님")
    t = TestClient(app)
    confirm(t, auth)
    tid = next(a["id"] for a in mem.accounts.values() if a.get("email") == "teach@example.com")
    assert t.get("/teacher/accounts").status_code == 403                     # 아직 학생
    admin = TestClient(app)
    admin.post("/login", data={"login_id": "admin", "password": "admin-pass-1"})
    assert "사용자 역할" in admin.get("/teacher/accounts").text
    admin.post("/admin/role", data={"account_id": tid, "role": "teacher"})
    t = TestClient(app)
    t.post("/login", data={"login_id": "teach@example.com", "password": "good-pass-1"})
    t.post("/teacher/accounts/class", data={"name": "논술 B반"})
    code = mem.class_list(tid)[0]["join_code"]
    assert re.fullmatch(r"[A-Z2-9]{6}", code)
    assert code in t.get("/teacher/accounts").text
    sid = acc["id"]
    assert t.get(f"/teacher/mvp/student/{sid}").status_code == 403           # 참여 전
    assert "찾지 못했어요" in other.post("/mvp/join", data={"code": "ZZZZZZ"}).text
    r = other.post("/mvp/join", data={"code": code.lower()})
    assert "참여했어요" in r.text
    other.post("/mvp/start")
    assert t.get(f"/teacher/mvp/student/{sid}").status_code == 200           # 참여 후 열람 가능
    assert sid in mem.states                                                 # 기록은 계정 id 로 저장


def test_password_reset_by_email(env):
    mem, auth = env
    c = TestClient(app)
    signup(c)
    confirm(c, auth)
    r = c.post("/forgot", data={"email": "nobody@example.com"})
    assert "보냈어요" in r.text and not [m for m in auth.outbox if m["to"] == "nobody@example.com"]
    c2 = TestClient(app)
    c2.post("/forgot", data={"email": "stu@example.com"})
    r = confirm(c2, auth, "recovery")
    assert r.json()["next"] == "/auth/reset"
    assert c2.post("/auth/reset", data={"new": "new-pass-22", "confirm": "nope"}).status_code == 400
    assert c2.post("/auth/reset", data={"new": "new-pass-22", "confirm": "new-pass-22"},
                   follow_redirects=False).status_code == 303
    assert TestClient(app).post("/login", data={"login_id": "stu@example.com", "password": "good-pass-1"}).status_code == 401
    assert TestClient(app).post("/login", data={"login_id": "stu@example.com", "password": "new-pass-22"},
                                follow_redirects=False).status_code == 303


def test_change_password_for_email_account(env):
    mem, auth = env
    c = TestClient(app)
    signup(c)
    confirm(c, auth)
    assert "맞지 않아요" in c.post("/account/password", data={"current": "wrong-pass", "new": "next-pass-9",
                                                            "confirm": "next-pass-9"}).text
    c.post("/account/password", data={"current": "good-pass-1", "new": "next-pass-9", "confirm": "next-pass-9"})
    assert TestClient(app).post("/login", data={"login_id": "stu@example.com", "password": "next-pass-9"},
                                follow_redirects=False).status_code == 303


def test_bad_callback_token(env):
    r = TestClient(app).post("/auth/session", json={"access_token": "forged", "type": "signup"})
    assert r.status_code == 400 and not r.json()["ok"]
