import os
from datetime import datetime, timezone
from functools import wraps
from typing import Optional

from flask import session, redirect, url_for, request
from supabase import create_client, Client


def _new_client() -> Client:
    """매 호출마다 새 클라이언트를 생성한다.

    클라이언트를 전역으로 캐싱해 재사용하면, 서로 다른 사용자의 요청이 동시에 처리될 때
    postgrest/auth에 실어둔 토큰(.postgrest.auth(token), .auth.set_session(...))이
    한 인스턴스에서 공유되어 요청 간에 뒤섞일 수 있다. 매번 새로 만들어 그 문제를 원천 차단한다.
    """
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_ANON_KEY"]
    return create_client(url, key)


def user_client(access_token: Optional[str] = None) -> Client:
    """요청 사용자의 access_token으로 인증된 클라이언트를 반환.

    이 토큰을 postgrest에 실어 보내면 Supabase RLS 정책의 auth.uid()가 해당 사용자로 평가되어,
    서비스 키 없이도 "본인 소유 행만 조회/삽입" 규칙이 그대로 적용된다.
    """
    token = access_token if access_token is not None else session.get("access_token")
    client = _new_client()
    if token:
        client.postgrest.auth(token)
    return client


def request_otp(email: str, *, signup_metadata: Optional[dict] = None):
    """이메일로 6자리 인증코드를 발송한다.

    signup_metadata가 주어지면(회원가입) 계정이 없을 때 새로 생성하며 해당 메타데이터를 저장한다.
    None이면(로그인) 기존 계정에만 코드를 보내고, 없는 이메일이면 오류가 발생한다.
    """
    options = {"should_create_user": signup_metadata is not None}
    if signup_metadata is not None:
        options["data"] = signup_metadata
    return _new_client().auth.sign_in_with_otp({"email": email, "options": options})


def verify_email_otp(email: str, token: str):
    return _new_client().auth.verify_otp({"email": email, "token": token, "type": "email"})


def update_company_url(access_token: str, refresh_token: str, company_url: str) -> None:
    """사용자가 분석을 실행할 때마다 사용한 홈페이지 주소를 기본값으로 갱신 저장한다."""
    client = _new_client()
    client.auth.set_session(access_token, refresh_token)
    client.auth.update_user({"data": {"company_url": company_url}})


def update_telegram_chat_id(access_token: str, refresh_token: str, chat_id: str) -> None:
    """텔레그램 딥링크 연동이 끝난 후 chat_id를 사용자 메타데이터에 저장한다."""
    client = _new_client()
    client.auth.set_session(access_token, refresh_token)
    client.auth.update_user({"data": {"telegram_chat_id": chat_id}})


def build_signup_metadata(
    *, company_url: str, company_name: str, contact_name: str, contact_phone: str,
    agree_service: bool, agree_privacy: bool, agree_marketing: bool,
) -> dict:
    return {
        "company_url": company_url,
        "company_name": company_name,
        "contact_name": contact_name,
        "contact_phone": contact_phone,
        "agree_service": agree_service,
        "agree_privacy": agree_privacy,
        "agree_marketing": agree_marketing,
        "consent_at": datetime.now(timezone.utc).isoformat(),
    }


def set_session(auth_session, user) -> None:
    meta = user.user_metadata or {}
    session["access_token"] = auth_session.access_token
    session["refresh_token"] = auth_session.refresh_token
    session["user_id"] = user.id
    session["email"] = user.email
    session["company_url"] = meta.get("company_url", "")
    session["company_name"] = meta.get("company_name", "")
    session["telegram_chat_id"] = meta.get("telegram_chat_id", "")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped
