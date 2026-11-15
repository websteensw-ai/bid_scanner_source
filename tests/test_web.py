"""웹앱(FastAPI) 테스트: 로그인, 수업 문답, 결과, 교사 화면. 저장소는 메모리."""
import re

import pytest
from fastapi.testclient import TestClient

from web import store as store_mod
from web.main import app


@pytest.fixture()
def client(monkeypatch):
    mem = store_mod.MemoryStore()
    monkeypatch.setattr("web.main.get_store", lambda: mem)
    return TestClient(app)


def login(c):
    return c.post("/login", data={"login_id": "test", "password": "testpoc"}, follow_redirects=True)


def test_login_page_and_wrong_password(client):
    r = client.get("/login")
    assert r.status_code == 200 and "테스트 계정" in r.text
    r = client.post("/login", data={"login_id": "test", "password": "x"})
    assert r.status_code == 401
    assert client.get("/home", follow_redirects=False).status_code == 303


def test_test_login_home(client):
    r = login(client)
    assert r.status_code == 200 and "6단계 논술 학습" in r.text
    r = client.get("/home")
    assert r.status_code == 200 and "오늘의 목표" in r.text


def test_each_browser_gets_own_demo_learner(client, monkeypatch):
    login(client)
    a = client.cookies.get("elenchos_session")
    other = TestClient(app)
    login(other)
    assert a != other.cookies.get("elenchos_session")


def test_lesson_dialogue_redirect_and_vocab(client):
    login(client)
    assert client.get("/learn/L1").status_code == 200
    r = client.post("/learn/L1/submit", data={"answer": "ㅋㅋㅋ 배고파요"}, headers={"HX-Request": "true"})
    assert r.status_code == 200 and "다시 과제로" in r.text and "잘 잡았어요" not in r.text
    assert "<html" not in r.text                                      # htmx 요청은 부분 화면만
    r = client.post("/learn/L1/submit", data={"answer": "공정이 무슨 뜻이에요?"},
                    headers={"HX-Request": "true"})
    assert "치우치지" in r.text


def test_lesson_progress_and_escape(client):
    login(client)
    client.get("/learn/L1")
    r = client.post("/learn/L1/submit", data={"answer": "<script>alert(1)</script> 장수 이야기"})
    assert "<script>alert(1)</script>" not in r.text                  # 학생 입력은 이스케이프
    r = client.post("/learn/L1/submit", data={
        "answer": "공정한 배분은 똑같이 나누는 것이 아니라 기여와 성과에 따라 보상을 달리하는 것이다",
        "evidence": "둘째 문단"})
    assert "새 글로 혼자 확인하기" in r.text                           # 일반화 단계 생략 후 독립 확인


def test_help_and_pause(client):
    login(client)
    client.get("/learn/L1")
    r = client.post("/learn/L1/help", data={"kind": "guide"}, headers={"HX-Request": "true"})
    assert "과제 안내" in r.text
    r = client.post("/learn/L1/pause", data={"answer": "쓰던 답"}, follow_redirects=True)
    assert "이어서 하기" in r.text


def test_teacher_pages_for_demo_admin(client):
    login(client)
    client.get("/learn/L1")
    for url in ("/teacher/records", "/teacher/records?tab=activity", "/teacher/content",
                "/teacher/content?tab=excerpts", "/teacher/quality", "/result", "/review",
                "/review?item=1-1"):
        r = client.get(url)
        assert r.status_code == 200, url
    # 데모 계정은 모든 학생에게 영향을 주는 자료 중지를 할 수 없음
    r = client.post("/teacher/content/status", data={"item": "L1", "status": "suspended", "note": "x"})
    assert r.status_code == 403


def test_teacher_override_rejudges(client):
    login(client)
    client.get("/learn/L1")
    sid = re.search(r'name="student" value="([^"]+)"', client.get("/teacher/records").text).group(1)
    r = client.post("/teacher/records/override", data={"student": sid, "criterion": "C1", "level": "3",
                                                      "note": "면담 확인"}, follow_redirects=True)
    assert "교사 수정: 면담 확인" in r.text


def test_healthz(client):
    assert client.get("/healthz").json()["ok"] is True
