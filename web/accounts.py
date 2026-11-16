"""계정·학급 (가이드 12·14장, 결정 1: 교사가 학급 단위로 학생 계정을 발급).

- 관리자: 교사 계정 발급, 모든 학급 열람
- 교사: 학급 만들기, 학생 계정 발급(여러 명 한꺼번에), 비밀번호 초기화, 사용 중지. 자기 학급 학생만 본다
- 학생: 발급받은 아이디로 로그인. 첫 로그인 때 비밀번호를 바꾼다
학생 실명·연락처는 받지 않는다. 비밀번호는 PBKDF2-SHA256 해시만 저장하고, 발급한 초기 비밀번호는
발급 화면에서 한 번만 보여 준다.
"""
import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Form, Request

import web.main as _main
from src.core.passwords import hash_pw, new_password, pw_problem, verify_pw
from web.main import Forbidden, redirect, render, require

router = APIRouter()

LOCK_AFTER = 5                 # 연속 실패 횟수
LOCK_MINUTES = 10
RECHECK_SECONDS = 600          # 세션 중 계정 사용 중지 여부 재확인 간격
_LOGIN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")


def _store():
    return _main.get_store()


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4)}"


# ---------------------------------------------------------------- 로그인
_DUMMY = hash_pw("timing-equalizer")


def authenticate(login_id: str, pw: str) -> tuple[dict | None, str | None]:
    """(세션 사용자, 오류 문구). 계정 유무를 드러내지 않도록 같은 문구를 쓴다."""
    generic = "아이디 또는 비밀번호를 확인해 주세요."
    login_id = login_id.strip().lower()
    if not login_id or not pw:
        return None, generic
    acc = _store().account_by_login(login_id)
    if not acc:
        verify_pw(pw, _DUMMY)                      # 응답 시간 차이로 계정 유무가 드러나지 않게
        return None, generic
    if acc.get("locked_until") and datetime.fromisoformat(acc["locked_until"]) > datetime.now(UTC):
        return None, f"로그인을 여러 번 실패해서 잠시 잠겼어요. {LOCK_MINUTES}분 뒤에 다시 해 주세요."
    if not verify_pw(pw, acc["pw_hash"]):
        fails = int(acc.get("failed_logins") or 0) + 1
        patch = {"failed_logins": fails}
        if fails >= LOCK_AFTER:
            patch |= {"failed_logins": 0,
                      "locked_until": (datetime.now(UTC) + timedelta(minutes=LOCK_MINUTES)).isoformat()}
        _store().account_update(acc["id"], patch)
        return None, generic
    if not acc.get("active", True):
        return None, "사용이 중지된 계정이에요. 선생님께 문의해 주세요."
    _store().account_update(acc["id"], {"failed_logins": 0, "locked_until": None, "last_login": True})
    _store().audit(acc["id"], "login")
    return session_user(acc), None


def session_user(acc: dict) -> dict:
    return {"id": acc["id"], "name": acc.get("display_name") or acc["login_id"], "login": acc["login_id"],
            "role": acc["role"], "is_demo": False, "must_change": bool(acc.get("must_change_pw")),
            "chk": now_iso()}


def recheck(request: Request, user: dict) -> dict | None:
    """세션 중에도 일정 간격으로 계정 상태를 다시 확인한다 (사용 중지 즉시 반영에 가깝게)."""
    if user.get("is_demo"):
        return user
    last = user.get("chk")
    if last and datetime.now(UTC) - datetime.fromisoformat(last) < timedelta(seconds=RECHECK_SECONDS):
        return user
    acc = _store().account_get(user["id"])
    if not acc or not acc.get("active", True):
        request.session.pop("user", None)
        return None
    fresh = session_user(acc)
    request.session["user"] = fresh
    return fresh


# ---------------------------------------------------------------- 볼 수 있는 학생
def visible_students(user: dict) -> list[dict]:
    """교사: 자기 학급 학생 / 관리자: 모든 학생 계정 / 데모: 자기 기록."""
    if user.get("is_demo"):
        return [{"id": user["id"], "display_name": "테스트 사용자 (내 기록)", "is_demo": True}]
    if user["role"] == "admin":
        accs = _store().account_list("student")
    else:
        seen, accs = set(), []
        for c in _store().class_list(user["id"]):
            for s in c["students"]:
                if s["id"] not in seen:
                    seen.add(s["id"])
                    accs.append({**s, "class": c["name"]})
    return [{"id": a["id"], "display_name": a.get("display_name") or a["login_id"], "login_id": a["login_id"],
             "is_demo": False, "class": a.get("class", "")} for a in accs]


def can_see(user: dict, student_id: str) -> bool:
    return student_id in {s["id"] for s in visible_students(user)}


def _my_classes(user: dict) -> list[dict]:
    return _store().class_list(None if user["role"] == "admin" else user["id"])


# ---------------------------------------------------------------- 비밀번호 변경
@router.get("/account/password")
def password_page(request: Request):
    user = require(request, allow_must_change=True)
    if user.get("is_demo"):
        return redirect("/")
    return render(request, "account_password.html", error=None, forced=user.get("must_change"))


@router.post("/account/password")
def password_change(request: Request, current: str = Form(""), new: str = Form(""), confirm: str = Form("")):
    user = require(request, allow_must_change=True)
    if user.get("is_demo"):
        return redirect("/")
    acc = _store().account_by_login(user["login"])

    def fail(msg):
        return render(request, "account_password.html", error=msg, forced=user.get("must_change"), status_code=400)

    if not acc or not verify_pw(current, acc["pw_hash"]):
        return fail("지금 비밀번호가 맞지 않아요.")
    if new != confirm:
        return fail("새 비밀번호 두 칸이 서로 달라요.")
    if new == current:
        return fail("지금과 다른 비밀번호를 써 주세요.")
    if (p := pw_problem(new, user["login"])):
        return fail(p)
    _store().account_update(acc["id"], {"pw_hash": hash_pw(new), "must_change_pw": False})
    _store().audit(acc["id"], "password_change")
    request.session["user"] = {**user, "must_change": False}
    return redirect("/")


# ---------------------------------------------------------------- 교사·관리자: 계정 관리
@router.get("/teacher/accounts")
def accounts_page(request: Request):
    user = require(request, "teacher")
    if user.get("is_demo"):
        return render(request, "accounts.html", demo=True, classes=[], teachers=[], issued=None)
    teachers = _store().account_list("teacher") if user["role"] == "admin" else []
    return render(request, "accounts.html", demo=False, classes=_my_classes(user), teachers=teachers, issued=None)


def _guard(request: Request):
    user = require(request, "teacher")
    if user.get("is_demo"):
        raise Forbidden()
    return user


@router.post("/teacher/accounts/class")
def class_create(request: Request, name: str = Form(""), teacher_id: str = Form("")):
    user = _guard(request)
    name = name.strip()[:60]
    if not name:
        return redirect("/teacher/accounts")
    owner = user["id"]
    if user["role"] == "admin" and teacher_id:
        if teacher_id not in {t["id"] for t in _store().account_list("teacher")}:
            raise Forbidden()
        owner = teacher_id
    cid = new_id("c")
    _store().class_create(cid, name, owner, "BASIC-Q1")
    _store().audit(user["id"], "class_create", cid)
    return redirect("/teacher/accounts")


def _class_of(user: dict, cid: str) -> dict:
    c = next((c for c in _my_classes(user) if c["id"] == cid), None)
    if not c:
        raise Forbidden()
    return c


@router.post("/teacher/accounts/issue")
def issue_students(request: Request, class_id: str = Form(...), prefix: str = Form(""), count: int = Form(0),
                   names: str = Form("")):
    """학생 계정 발급. 이름 목록(한 줄에 한 명, 선택)이 있으면 그 수만큼, 없으면 count 만큼."""
    user = _guard(request)
    c = _class_of(user, class_id)
    prefix = prefix.strip().lower()
    if not _LOGIN_RE.match(prefix + "01"):
        return render(request, "accounts.html", demo=False, classes=_my_classes(user), issued=None,
                      teachers=_store().account_list("teacher") if user["role"] == "admin" else [],
                      error="아이디 앞부분은 영문 소문자·숫자·.-_ 로 2~28자로 써 주세요. 예) 2026a")
    name_list = [n.strip()[:30] for n in names.splitlines() if n.strip()]
    n = len(name_list) or max(0, min(int(count or 0), 60))
    taken = {a["login_id"] for a in _store().account_list(None)}
    issued, k = [], 0
    while len(issued) < n and k < n + 500:
        k += 1
        login = f"{prefix}{k:02d}"
        if login in taken:
            continue
        pw = new_password()
        aid = new_id("u")
        disp = name_list[len(issued)] if name_list else login
        _store().account_create(aid, login, hash_pw(pw), "student", disp, user["id"])
        _store().class_add_member(class_id, aid)
        issued.append({"login_id": login, "password": pw, "display_name": disp})
    _store().audit(user["id"], "issue_students", f"{class_id}:{len(issued)}")
    return render(request, "accounts.html", demo=False, classes=_my_classes(user), issued=issued,
                  issued_class=c["name"], teachers=_store().account_list("teacher") if user["role"] == "admin" else [])


@router.post("/teacher/accounts/reset")
def reset_password(request: Request, student_id: str = Form(...)):
    user = _guard(request)
    target = _store().account_get(student_id)
    if not target or not (can_see(user, student_id) or (user["role"] == "admin" and target["role"] == "teacher")):
        raise Forbidden()
    pw = new_password()
    _store().account_update(student_id, {"pw_hash": hash_pw(pw), "must_change_pw": True, "failed_logins": 0,
                                         "locked_until": None})
    _store().audit(user["id"], "password_reset", student_id)
    return render(request, "accounts.html", demo=False, classes=_my_classes(user),
                  teachers=_store().account_list("teacher") if user["role"] == "admin" else [],
                  issued=[{"login_id": target["login_id"], "password": pw, "display_name": target["display_name"]}],
                  issued_class="비밀번호 초기화")


@router.post("/teacher/accounts/active")
def set_active(request: Request, student_id: str = Form(...), active: str = Form("0")):
    user = _guard(request)
    target = _store().account_get(student_id)
    if not target or not (can_see(user, student_id) or (user["role"] == "admin" and target["role"] == "teacher")):
        raise Forbidden()
    _store().account_update(student_id, {"active": active == "1"})
    _store().audit(user["id"], "activate" if active == "1" else "deactivate", student_id)
    return redirect("/teacher/accounts")


@router.post("/admin/teachers")
def create_teacher(request: Request, login_id: str = Form(""), display_name: str = Form("")):
    user = require(request, "admin")
    if user.get("is_demo") or user["role"] != "admin":
        raise Forbidden()
    login = login_id.strip().lower()
    err = None
    if not _LOGIN_RE.match(login):
        err = "아이디는 영문 소문자·숫자·.-_ 로 3~32자로 써 주세요."
    elif _store().account_by_login(login):
        err = "이미 있는 아이디예요."
    if err:
        return render(request, "accounts.html", demo=False, classes=_my_classes(user), issued=None,
                      teachers=_store().account_list("teacher"), error=err)
    pw = new_password(10)
    aid = new_id("u")
    _store().account_create(aid, login, hash_pw(pw), "teacher", display_name.strip()[:30] or login, user["id"])
    _store().audit(user["id"], "teacher_create", aid)
    return render(request, "accounts.html", demo=False, classes=_my_classes(user),
                  teachers=_store().account_list("teacher"),
                  issued=[{"login_id": login, "password": pw, "display_name": display_name or login}],
                  issued_class="교사 계정")
