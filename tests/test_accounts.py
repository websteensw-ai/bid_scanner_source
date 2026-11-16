"""계정·학급 테스트: 비밀번호 해시, 로그인·잠금, 첫 로그인 변경, 학급 발급, 교사별 열람 범위, 계정별 기록."""
import re

import pytest
from fastapi.testclient import TestClient

from web import store as store_mod
from web.accounts import hash_pw, verify_pw
from web.main import app


@pytest.fixture()
def mem(monkeypatch):
    m = store_mod.MemoryStore()
    monkeypatch.setattr("web.main.get_store", lambda: m)
    m.account_create("u-admin", "admin", hash_pw("admin-pass-1"), "admin", "관리자", "seed")
    m.account_update("u-admin", {"must_change_pw": False})
    return m


def login(c, lid, pw):
    return c.post("/login", data={"login_id": lid, "password": pw}, follow_redirects=False)


def test_hash_roundtrip():
    h = hash_pw("abcd1234")
    assert h.startswith("pbkdf2_sha256$") and "abcd1234" not in h
    assert verify_pw("abcd1234", h) and not verify_pw("abcd1235", h)
    assert hash_pw("abcd1234") != h                    # salt


def test_login_lockout_and_generic_error(mem):
    c = TestClient(app)
    r = login(c, "nobody", "x")
    assert r.status_code == 401 and "아이디 또는 비밀번호" in r.text
    for _ in range(5):
        login(c, "admin", "wrong")
    r = login(c, "admin", "admin-pass-1")
    assert r.status_code == 401 and "잠시 잠겼어요" in r.text


def issue(c, cid, prefix="26a", count=3):
    r = c.post("/teacher/accounts/issue", data={"class_id": cid, "prefix": prefix, "count": count})
    return re.findall(r"<code>([a-z0-9]+)</code></td><td><code>([a-z0-9]+)</code>", r.text)


def test_full_account_flow(mem):
    admin = TestClient(app)
    assert login(admin, "admin", "admin-pass-1").headers["location"] == "/"
    # 교사 두 명 발급
    r = admin.post("/admin/teachers", data={"login_id": "kim.t", "display_name": "김 선생님"})
    kim_pw = re.search(r"<code>kim\.t</code></td><td><code>([a-z0-9]+)</code>", r.text).group(1)
    r = admin.post("/admin/teachers", data={"login_id": "lee.t", "display_name": "이 선생님"})
    lee_pw = re.search(r"<code>lee\.t</code></td><td><code>([a-z0-9]+)</code>", r.text).group(1)
    # 교사 첫 로그인 → 비밀번호 변경 강제
    kim = TestClient(app)
    assert login(kim, "kim.t", kim_pw).headers["location"] == "/account/password"
    assert kim.get("/teacher/mvp", follow_redirects=False).headers["location"] == "/account/password"
    r = kim.post("/account/password", data={"current": kim_pw, "new": "12345678", "confirm": "12345678"})
    assert r.status_code == 400                         # 숫자만 → 거절
    r = kim.post("/account/password", data={"current": kim_pw, "new": "kim-secret-9", "confirm": "kim-secret-9"},
                 follow_redirects=False)
    assert r.status_code == 303
    assert kim.get("/teacher/mvp").status_code == 200
    # 학급 만들고 학생 발급
    kim.post("/teacher/accounts/class", data={"name": "논술 A반"})
    cid = mem.class_list(next(a["id"] for a in mem.accounts.values() if a["login_id"] == "kim.t"))[0]["id"]
    creds = issue(kim, cid)
    assert [x[0] for x in creds] == ["26a01", "26a02", "26a03"]
    assert all(mem.account_by_login(x[0])["pw_hash"] != x[1] for x in creds)   # 평문 저장 안 함
    # 학생 로그인 → 비밀번호 변경 → 학습 → 계정 id 로 저장
    st = TestClient(app)
    assert login(st, *creds[0]).headers["location"] == "/account/password"
    st.post("/account/password", data={"current": creds[0][1], "new": "student-pw-1", "confirm": "student-pw-1"})
    st.post("/mvp/start")
    sid = mem.account_by_login("26a01")["id"]
    assert sid in mem.states and mem.states[sid]["mvp"]
    # 다른 기기(새 브라우저)에서 같은 계정으로 이어서
    st2 = TestClient(app)
    login(st2, "26a01", "student-pw-1")
    st2.post("/mvp/guide/done")
    assert "이어서 하기" in st2.get("/mvp").text
    # 학생은 교사 화면 불가
    assert st.get("/teacher/accounts").status_code == 403
    # 열람 범위: 김 선생님은 자기 학생, 이 선생님은 볼 수 없음
    assert kim.get(f"/teacher/mvp/student/{sid}").status_code == 200
    lee = TestClient(app)
    login(lee, "lee.t", lee_pw)
    lee.post("/account/password", data={"current": lee_pw, "new": "lee-secret-9", "confirm": "lee-secret-9"})
    assert lee.get(f"/teacher/mvp/student/{sid}").status_code == 403
    assert lee.post("/teacher/accounts/reset", data={"student_id": sid}).status_code == 403
    assert admin.get(f"/teacher/mvp/student/{sid}").status_code == 200
    # 사용 중지 → 다음 로그인 거부
    kim.post("/teacher/accounts/active", data={"student_id": sid, "active": "0"})
    r = login(TestClient(app), "26a01", "student-pw-1")
    assert r.status_code == 401 and "사용이 중지된" in r.text
    # 비밀번호 초기화 → 새 임시 비밀번호로 로그인하면 다시 변경 강제
    kim.post("/teacher/accounts/active", data={"student_id": sid, "active": "1"})
    r = kim.post("/teacher/accounts/reset", data={"student_id": sid})
    newpw = re.search(r"<code>26a01</code></td><td><code>([a-z0-9]+)</code>", r.text).group(1)
    assert login(TestClient(app), "26a01", newpw).headers["location"] == "/account/password"
    assert any(a["action"] == "issue_students" for a in mem.audits)


def test_demo_cannot_issue(mem):
    c = TestClient(app)
    c.post("/login", data={"login_id": "test", "password": "testpoc"})
    assert "테스트 계정에서는" in c.get("/teacher/accounts").text
    assert c.post("/teacher/accounts/class", data={"name": "x"}).status_code == 403


def test_foundation_pages_open_for_real_accounts_without_ai_key(mem):
    """AI 키가 없어도 실제 계정으로 기초 다지기 화면이 열린다 (데모 분석기로 동작)."""
    c = TestClient(app)
    login(c, "admin", "admin-pass-1")
    for p in ["/home", "/result", "/review"]:
        assert c.get(p).status_code == 200, p
