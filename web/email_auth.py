"""이메일 인증 코드(OTP) 로그인과 학급 코드 참여.

흐름 (가입과 로그인이 같다)
1. 이메일 입력 → Supabase Auth 가 6자리 인증 코드를 메일로 보냄 (처음 쓰는 이메일이면 사용자도 생성)
2. 코드 입력 → 확인되면 로그인. 처음이면 elenchos.accounts 에 학생 계정을 만들고
3. 처음 한 번만 '시작 정보'(표시 이름·동의·만 14세 이상) 입력 → 학급 코드로 학급 참여
비밀번호가 없으므로 비밀번호 분실·재설정 절차가 필요 없다.
아이디 계정(관리자·교사가 발급, 이메일이 없는 학생)은 기존처럼 아이디·비밀번호로 로그인한다.
역할은 모두 학생으로 시작하고, 교사 권한은 관리자가 계정·학급 관리에서 준다.
"""
import os
import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

import web.main as _main
from web.accounts import new_id, session_user
from web.main import redirect, render, require
from web.supa_auth import AuthError, get_auth

router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
RESEND_SECONDS = 60
MAX_TRIES = 5
MESSAGES = {
    "bad_code": "인증 코드가 맞지 않거나 시간이 지났어요. 메일의 코드를 다시 확인하거나 새 코드를 받아 주세요.",
    "rate_limited": "요청이 많아 잠시 막혔어요. 1~2분 뒤에 다시 해 주세요.",
    "bad_email": "이메일 주소 형식을 확인해 주세요.",
    "mail_blocked": "지금은 이 주소로 인증 메일을 보낼 수 없어요 (메일 발송 설정 준비 중). 관리자에게 알려 주세요.",
    "invalid_token": "링크가 만료되었거나 이미 사용되었어요. 인증 코드로 다시 로그인해 주세요.",
    "unknown": "처리하지 못했어요. 잠시 뒤 다시 해 주세요.",
}
CONSENT_ITEMS = [
    ("service", "서비스 이용약관과 개인정보 처리에 동의해요 (필수)", True),
    ("ai", "내가 쓴 답과 글이 튜터 문답과 채점을 위해 외부 언어 모델 서비스로 전송되는 것에 동의해요 (필수, 이름은 보내지 않아요)", True),
    ("teacher", "참여한 학급의 담당 선생님이 내 학습 기록을 보는 것에 동의해요 (필수)", True),
    ("research", "이름을 지운 기록을 서비스 개선·연구에 쓰는 것에 동의해요 (선택)", False),
]


def _store():
    return _main.get_store()


def _msg(e: AuthError) -> str:
    return MESSAGES.get(e.code, MESSAGES["unknown"])


def site_url(request: Request) -> str:
    if (s := os.getenv("SITE_URL")):
        return s.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def start_session(request: Request, acc: dict) -> None:
    demo_id = request.session.get("demo_id")
    request.session.clear()
    if demo_id:
        request.session["demo_id"] = demo_id
    request.session["user"] = session_user(acc)


def _account_for(user_id: str, email: str) -> dict:
    acc = _store().account_by_auth(user_id)
    if not acc:
        _store().account_create_auth(new_id("u"), user_id, email, "", {})
        acc = _store().account_by_auth(user_id)
        _store().audit(acc["id"], "signup_otp")
    return acc


def _code_page(request: Request, email: str, error: str | None = None, status: int = 200, resent: bool = False):
    return render(request, "login_code.html", email=email, error=error, resent=resent, status_code=status)


# ---------------------------------------------------------------- 1. 코드 받기
@router.get("/signup")
def signup_page():
    return redirect("/login")              # 가입과 로그인은 같은 화면 (이메일 인증 코드)


@router.post("/login/code")
def send_code(request: Request, email: str = Form("")):
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        return render(request, "login.html", settings=_main.settings, error=MESSAGES["bad_email"], status_code=400)
    try:
        get_auth().send_otp(email)
    except AuthError as e:
        return render(request, "login.html", settings=_main.settings, error=_msg(e), status_code=400)
    except Exception:
        return render(request, "login.html", settings=_main.settings, error=MESSAGES["unknown"], status_code=502)
    request.session["otp"] = {"email": email, "sent": datetime.now(UTC).isoformat(), "tries": 0}
    return _code_page(request, email)


@router.post("/login/code/resend")
def resend_code(request: Request):
    st = request.session.get("otp")
    if not st:
        return redirect("/login")
    wait = RESEND_SECONDS - (datetime.now(UTC) - datetime.fromisoformat(st["sent"])).total_seconds()
    if wait > 0:
        return _code_page(request, st["email"], f"{int(wait) + 1}초 뒤에 다시 받을 수 있어요.", 429)
    try:
        get_auth().send_otp(st["email"])
    except AuthError as e:
        return _code_page(request, st["email"], _msg(e), 400)
    request.session["otp"] = {**st, "sent": datetime.now(UTC).isoformat(), "tries": 0}
    return _code_page(request, st["email"], resent=True)


# ---------------------------------------------------------------- 2. 코드 확인
@router.post("/login/verify")
def verify_code(request: Request, code: str = Form("")):
    st = request.session.get("otp")
    if not st:
        return redirect("/login")
    if datetime.now(UTC) - datetime.fromisoformat(st["sent"]) > timedelta(hours=1):
        request.session.pop("otp", None)
        return render(request, "login.html", settings=_main.settings, error=MESSAGES["bad_code"], status_code=400)
    if st["tries"] >= MAX_TRIES:
        return _code_page(request, st["email"], "여러 번 틀렸어요. 새 코드를 받아 주세요.", 429)
    code = re.sub(r"\D", "", code)
    try:
        r = get_auth().verify_otp(st["email"], code)
    except AuthError as e:
        request.session["otp"] = {**st, "tries": st["tries"] + 1}
        return _code_page(request, st["email"], _msg(e), 400)
    except Exception:
        return _code_page(request, st["email"], MESSAGES["unknown"], 502)
    acc = _account_for(r["user_id"], r["email"])
    if not acc.get("active", True):
        request.session.pop("otp", None)
        return render(request, "login.html", settings=_main.settings, status_code=403,
                      error="사용이 중지된 계정이에요. 선생님께 문의해 주세요.")
    _store().account_update(acc["id"], {"last_login": True})
    _store().audit(acc["id"], "login_otp")
    start_session(request, acc)
    return redirect("/welcome" if request.session["user"].get("needs_profile") else "/")


# ---------------------------------------------------------------- 3. 처음 한 번: 시작 정보
@router.get("/welcome")
def welcome_page(request: Request):
    user = require(request)
    if not user.get("needs_profile"):
        return redirect("/")
    return render(request, "welcome.html", consent_items=CONSENT_ITEMS, error=None, form={})


@router.post("/welcome")
async def welcome(request: Request):
    user = require(request)
    form = await request.form()
    name = str(form.get("display_name", "")).strip()[:30]
    consent = {k: form.get(f"c_{k}") == "1" for k, _, _ in CONSENT_ITEMS}

    def fail(msg):
        return render(request, "welcome.html", consent_items=CONSENT_ITEMS, error=msg, form={"display_name": name},
                      status_code=400)

    if not name:
        return fail("표시 이름을 적어 주세요. 실명 대신 별칭도 괜찮아요.")
    if not all(consent[k] for k, _, req in CONSENT_ITEMS if req):
        return fail("필수 동의 항목에 모두 동의해야 시작할 수 있어요.")
    if form.get("age14") != "1":
        return fail("만 14세 미만은 보호자 동의가 필요해요. 선생님께 발급 계정을 요청해 주세요.")
    from src.learning.state import now
    _store().account_update(user["id"], {"display_name": name, "consent": {**consent, "age14": True, "at": now()}})
    _store().audit(user["id"], "consent")
    acc = _store().account_get(user["id"])
    request.session["user"] = session_user(acc)
    return redirect("/mvp/join" if acc["role"] == "student" else "/")


# ---------------------------------------------------------------- 메일이 링크로 온 경우 (템플릿이 링크형일 때 대비)
@router.get("/auth/callback")
def auth_callback(request: Request):
    return render(request, "auth_callback.html")


@router.post("/auth/session")
async def auth_session(request: Request):
    data = await request.json()
    try:
        u = get_auth().user_from_token(str(data.get("access_token", "")))
    except AuthError as e:
        return JSONResponse({"ok": False, "error": _msg(e)}, status_code=400)
    acc = _account_for(u["user_id"], u["email"])
    if not acc.get("active", True):
        return JSONResponse({"ok": False, "error": "사용이 중지된 계정이에요."}, status_code=403)
    start_session(request, acc)
    return JSONResponse({"ok": True, "next": "/welcome" if request.session["user"].get("needs_profile") else "/"})


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
