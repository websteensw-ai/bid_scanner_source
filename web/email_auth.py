"""이메일 가입·로그인·비밀번호 재설정과 학급 코드 참여.

흐름
- 가입: 이메일·비밀번호·표시 이름·동의 → Supabase Auth 가입 → elenchos.accounts 에 학생 계정 생성
  → (프로젝트 설정에 따라) 인증 메일의 링크 → /auth/callback → 로그인
- 로그인: 이메일이면 Supabase Auth, 아이디면 기존 발급 계정(관리자·교사 발급 학생)
- 비밀번호 찾기: 재설정 메일 → /auth/callback (type=recovery) → 새 비밀번호
- 학급 참여: 교사가 알려 준 학급 코드 입력 → 그 학급 학생이 되어 담당 교사가 기록을 본다
역할은 가입 시 모두 학생이고, 교사 권한은 관리자가 계정·학급 관리에서 준다.
"""
import os
import re
import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

import web.main as _main
from src.core.passwords import pw_problem
from web.accounts import new_id, session_user
from web.main import redirect, render, require
from web.supa_auth import AuthError, get_auth

router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
MESSAGES = {
    "exists": "이미 가입한 이메일이에요. 로그인하거나 비밀번호 찾기를 이용해 주세요.",
    "not_confirmed": "아직 이메일 인증을 하지 않았어요. 받은편지함(스팸함 포함)의 인증 메일 링크를 눌러 주세요.",
    "invalid": "이메일 또는 비밀번호를 확인해 주세요.",
    "rate_limited": "요청이 많아 잠시 막혔어요. 몇 분 뒤에 다시 해 주세요.",
    "weak_password": "비밀번호가 너무 쉬워요. 8자 이상으로 다른 비밀번호를 써 주세요.",
    "bad_email": "이메일 주소 형식을 확인해 주세요.",
    "invalid_token": "링크가 만료되었거나 이미 사용되었어요. 다시 요청해 주세요.",
    "unknown": "처리하지 못했어요. 잠시 뒤 다시 해 주세요.",
}
CONSENT_ITEMS = [
    ("service", "서비스 이용약관과 개인정보 처리에 동의해요 (필수)", True),
    ("ai", "내가 쓴 답과 글이 AI 분석을 위해 외부 AI 서비스로 전송되는 것에 동의해요 (필수, 이름은 보내지 않아요)", True),
    ("teacher", "참여한 학급의 담당 선생님이 내 학습 기록을 보는 것에 동의해요 (필수)", True),
    ("research", "이름을 지운 기록을 서비스 개선·연구에 쓰는 것에 동의해요 (선택)", False),
]


def _store():
    return _main.get_store()


def site_url(request: Request) -> str:
    """인증 메일 링크가 돌아올 주소. SITE_URL 환경 변수가 있으면 그것을 쓴다."""
    if (s := os.getenv("SITE_URL")):
        return s.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def _msg(e: AuthError) -> str:
    return MESSAGES.get(e.code, MESSAGES["unknown"])


def start_session(request: Request, acc: dict) -> None:
    demo_id = request.session.get("demo_id")
    request.session.clear()
    if demo_id:
        request.session["demo_id"] = demo_id
    request.session["user"] = session_user(acc)


def email_login(email: str, password: str) -> tuple[dict | None, str | None]:
    try:
        r = get_auth().sign_in(email.strip().lower(), password)
    except AuthError as e:
        return None, _msg(e)
    except Exception:
        return None, "로그인 서버에 연결하지 못했어요. 잠시 뒤 다시 해 주세요."
    acc = _store().account_by_auth(r["user_id"])
    if not acc:                                   # 다른 경로로 만든 Auth 사용자 → 학생 계정 생성
        _store().account_create_auth(new_id("u"), r["user_id"], r["email"], r["email"].split("@")[0], {})
        acc = _store().account_by_auth(r["user_id"])
    if not acc.get("active", True):
        return None, "사용이 중지된 계정이에요. 선생님께 문의해 주세요."
    _store().account_update(acc["id"], {"last_login": True})
    _store().audit(acc["id"], "login_email")
    return acc, None


# ---------------------------------------------------------------- 가입
@router.get("/signup")
def signup_page(request: Request):
    if _main.current_user(request):
        return redirect("/")
    return render(request, "signup.html", consent_items=CONSENT_ITEMS, error=None, form={}, sent=None)


@router.post("/signup")
async def signup(request: Request):
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    pw, pw2 = str(form.get("password", "")), str(form.get("confirm", ""))
    name = str(form.get("display_name", "")).strip()[:30]
    consent = {k: form.get(f"c_{k}") == "1" for k, _, _ in CONSENT_ITEMS}
    keep = {"email": email, "display_name": name}

    def fail(msg):
        return render(request, "signup.html", consent_items=CONSENT_ITEMS, error=msg, form=keep, sent=None,
                      status_code=400)

    if not _EMAIL_RE.match(email):
        return fail(MESSAGES["bad_email"])
    if pw != pw2:
        return fail("비밀번호 두 칸이 서로 달라요.")
    if (p := pw_problem(pw, email.split("@")[0])):
        return fail(p)
    if not name:
        return fail("표시 이름을 적어 주세요. 실명 대신 별칭도 괜찮아요.")
    if not all(consent[k] for k, _, req in CONSENT_ITEMS if req):
        return fail("필수 동의 항목에 모두 동의해야 가입할 수 있어요.")
    if form.get("age14") != "1":
        return fail("만 14세 미만은 보호자 동의가 필요해요. 선생님께 발급 계정을 요청해 주세요.")
    try:
        r = get_auth().sign_up(email, pw, f"{site_url(request)}/auth/callback")
    except AuthError as e:
        return fail(_msg(e))
    except Exception:
        return fail("가입 서버에 연결하지 못했어요. 잠시 뒤 다시 해 주세요.")
    from src.learning.state import now
    _store().account_create_auth(new_id("u"), r["user_id"], email, name, {**consent, "age14": True, "at": now()})
    acc = _store().account_by_auth(r["user_id"])
    _store().audit(acc["id"] if acc else r["user_id"], "signup")
    if r["confirmed"] and acc:
        start_session(request, acc)
        return redirect("/mvp/join")
    return render(request, "signup.html", consent_items=CONSENT_ITEMS, error=None, form={}, sent=email)


@router.post("/signup/resend")
def resend(request: Request, email: str = Form("")):
    try:
        get_auth().resend_confirmation(email.strip().lower(), f"{site_url(request)}/auth/callback")
    except AuthError as e:
        return render(request, "signup.html", consent_items=CONSENT_ITEMS, error=_msg(e), form={}, sent=email)
    except Exception:
        pass
    return render(request, "signup.html", consent_items=CONSENT_ITEMS, error=None, form={}, sent=email, resent=True)


# ---------------------------------------------------------------- 메일 링크 돌아오기
@router.get("/auth/callback")
def auth_callback(request: Request):
    """Supabase 는 토큰을 URL 조각(#access_token=…)으로 돌려주므로, 작은 스크립트가 서버로 보낸다."""
    return render(request, "auth_callback.html")


@router.post("/auth/session")
async def auth_session(request: Request):
    data = await request.json()
    token, kind = str(data.get("access_token", "")), str(data.get("type", ""))
    try:
        u = get_auth().user_from_token(token)
    except AuthError as e:
        return JSONResponse({"ok": False, "error": _msg(e)}, status_code=400)
    acc = _store().account_by_auth(u["user_id"])
    if not acc:
        _store().account_create_auth(new_id("u"), u["user_id"], u["email"], u["email"].split("@")[0], {})
        acc = _store().account_by_auth(u["user_id"])
    if not acc.get("active", True):
        return JSONResponse({"ok": False, "error": "사용이 중지된 계정이에요."}, status_code=403)
    start_session(request, acc)
    if kind == "recovery":
        request.session["reset_token"] = token
        return JSONResponse({"ok": True, "next": "/auth/reset"})
    _store().audit(acc["id"], "email_confirmed")
    return JSONResponse({"ok": True, "next": "/mvp/join" if acc["role"] == "student" else "/"})


# ---------------------------------------------------------------- 비밀번호 찾기·재설정
@router.get("/forgot")
def forgot_page(request: Request):
    return render(request, "forgot.html", sent=False, error=None)


@router.post("/forgot")
def forgot(request: Request, email: str = Form("")):
    email = email.strip().lower()
    if _EMAIL_RE.match(email):
        try:
            get_auth().send_reset(email, f"{site_url(request)}/auth/callback")
        except AuthError as e:
            if e.code == "rate_limited":
                return render(request, "forgot.html", sent=False, error=_msg(e))
        except Exception:
            return render(request, "forgot.html", sent=False, error=MESSAGES["unknown"])
    return render(request, "forgot.html", sent=True, error=None)      # 가입 여부를 드러내지 않음


@router.get("/auth/reset")
def reset_page(request: Request):
    require(request)
    if not request.session.get("reset_token"):
        return redirect("/forgot")
    return render(request, "auth_reset.html", error=None)


@router.post("/auth/reset")
def reset(request: Request, new: str = Form(""), confirm: str = Form("")):
    user = require(request)
    token = request.session.get("reset_token")
    if not token:
        return redirect("/forgot")
    if new != confirm:
        return render(request, "auth_reset.html", error="새 비밀번호 두 칸이 서로 달라요.", status_code=400)
    if (p := pw_problem(new, user.get("login", ""))):
        return render(request, "auth_reset.html", error=p, status_code=400)
    try:
        get_auth().set_password(token, new)
    except AuthError as e:
        return render(request, "auth_reset.html", error=_msg(e), status_code=400)
    request.session.pop("reset_token", None)
    _store().audit(user["id"], "password_reset_email")
    return redirect("/")


def change_email_password(user: dict, current: str, new: str) -> str | None:
    """이메일 계정의 비밀번호 변경: 지금 비밀번호로 다시 로그인해 토큰을 받고 바꾼다."""
    acc = _store().account_get(user["id"])
    try:
        r = get_auth().sign_in(acc["email"], current)
    except AuthError:
        return "지금 비밀번호가 맞지 않아요."
    try:
        get_auth().set_password(r["access_token"], new)
    except AuthError as e:
        return _msg(e)
    return None


# ---------------------------------------------------------------- 학급 코드
def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))


@router.get("/mvp/join")
def join_page(request: Request):
    user = require(request, "student")
    mine = [] if user.get("is_demo") else _store().classes_of_student(user["id"])
    return render(request, "join.html", mine=mine, error=None, joined=None)


@router.post("/mvp/join")
def join(request: Request, code: str = Form("")):
    user = require(request, "student")
    if user.get("is_demo"):
        return render(request, "join.html", mine=[], error="테스트 계정은 학급에 참여할 수 없어요.", joined=None)
    c = _store().class_by_code(re.sub(r"[^A-Za-z0-9]", "", code)[:12]) if code.strip() else None
    if not c:
        return render(request, "join.html", mine=_store().classes_of_student(user["id"]),
                      error="학급 코드를 찾지 못했어요. 선생님께 다시 확인해 주세요.", joined=None, status_code=400)
    _store().class_add_member(c["id"], user["id"])
    _store().audit(user["id"], "class_join", c["id"])
    return render(request, "join.html", mine=_store().classes_of_student(user["id"]), error=None, joined=c["name"])
