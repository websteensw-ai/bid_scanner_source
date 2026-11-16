"""Supabase Auth (이메일·비밀번호) 클라이언트.

비밀번호 확인·인증 메일·비밀번호 재설정 메일은 Supabase Auth 가 맡는다. 앱 서버만 호출하며
브라우저에는 Supabase 토큰을 넘기지 않는다(세션은 앱의 서명 쿠키).
- SupabaseAuth: 운영 (SUPABASE_URL, SUPABASE_ANON_KEY)
- MemoryAuth: 로컬·테스트 (프로세스 메모리, 인증 메일 대신 확인 토큰을 바로 돌려준다)
"""
import os
import secrets
from functools import lru_cache

import httpx

from src.core.passwords import hash_pw, verify_pw


class AuthError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _ko(code: str, msg: str) -> AuthError:
    """Supabase Auth 오류 → 학생에게 보일 문구 코드."""
    m = (msg or "").lower()
    if code == "otp_expired" or "expired" in m or ("token" in m and "invalid" in m):
        return AuthError("bad_code")
    if code == "email_address_not_authorized" or "not authorized" in m:
        return AuthError("mail_blocked")
    if "already" in m or "registered" in m or code == "user_already_exists":
        return AuthError("exists")
    if "not confirmed" in m or code == "email_not_confirmed":
        return AuthError("not_confirmed")
    if "invalid login" in m or code == "invalid_credentials":
        return AuthError("invalid")
    if "rate" in m or code in ("over_email_send_rate_limit", "over_request_rate_limit"):
        return AuthError("rate_limited")
    if "password" in m and ("weak" in m or "least" in m or "short" in m):
        return AuthError("weak_password")
    if "email" in m and "invalid" in m:
        return AuthError("bad_email")
    return AuthError("unknown", msg)


class Auth:
    def sign_up(self, email: str, password: str, redirect_to: str) -> dict:
        """{'user_id', 'email', 'confirmed': bool}. 이미 있는 이메일이면 AuthError('exists')."""
        raise NotImplementedError

    def sign_in(self, email: str, password: str) -> dict:
        """{'user_id', 'email', 'access_token'}."""
        raise NotImplementedError

    def user_from_token(self, access_token: str) -> dict:
        raise NotImplementedError

    def send_reset(self, email: str, redirect_to: str) -> None:
        raise NotImplementedError

    def set_password(self, access_token: str, new_password: str) -> None:
        raise NotImplementedError

    def resend_confirmation(self, email: str, redirect_to: str) -> None:
        raise NotImplementedError

    def send_otp(self, email: str) -> None:
        """이메일로 6자리 인증 코드를 보낸다. 처음 쓰는 이메일이면 Auth 사용자도 만든다."""
        raise NotImplementedError

    def verify_otp(self, email: str, code: str) -> dict:
        """{'user_id', 'email'}. 틀리거나 만료되면 AuthError('bad_code')."""
        raise NotImplementedError


class SupabaseAuth(Auth):
    def __init__(self, url: str, anon_key: str):
        self.base = url.rstrip("/") + "/auth/v1"
        self.key = anon_key
        self.client = httpx.Client(timeout=15)

    def _h(self, token: str | None = None) -> dict:
        return {"apikey": self.key, "Authorization": f"Bearer {token or self.key}", "Content-Type": "application/json"}

    def _post(self, path: str, body: dict, token: str | None = None, params: dict | None = None) -> dict:
        r = self.client.post(self.base + path, json=body, headers=self._h(token), params=params)
        data = r.json() if r.content else {}
        if r.status_code >= 400:
            raise _ko(str(data.get("error_code") or data.get("code") or ""),
                      str(data.get("msg") or data.get("message") or data.get("error_description") or r.text[:200]))
        return data

    def sign_up(self, email, password, redirect_to):
        d = self._post("/signup", {"email": email, "password": password}, params={"redirect_to": redirect_to})
        user = d.get("user") or d
        if not user.get("id"):
            raise AuthError("unknown", "가입 응답 형식 오류")
        # 이미 가입된(확인된) 이메일이면 Supabase 는 오류 대신 identities 가 빈 사용자를 돌려준다
        if user.get("identities") == []:
            raise AuthError("exists")
        return {"user_id": user["id"], "email": user.get("email", email),
                "confirmed": bool(user.get("email_confirmed_at") or d.get("access_token"))}

    def sign_in(self, email, password):
        d = self._post("/token", {"email": email, "password": password}, params={"grant_type": "password"})
        u = d.get("user") or {}
        return {"user_id": u["id"], "email": u.get("email", email), "access_token": d["access_token"]}

    def user_from_token(self, access_token):
        r = self.client.get(self.base + "/user", headers=self._h(access_token))
        if r.status_code >= 400:
            raise AuthError("invalid_token")
        u = r.json()
        return {"user_id": u["id"], "email": u.get("email", ""), "confirmed": bool(u.get("email_confirmed_at"))}

    def send_reset(self, email, redirect_to):
        self._post("/recover", {"email": email}, params={"redirect_to": redirect_to})

    def set_password(self, access_token, new_password):
        r = self.client.put(self.base + "/user", json={"password": new_password}, headers=self._h(access_token))
        if r.status_code >= 400:
            d = r.json() if r.content else {}
            raise _ko(str(d.get("error_code") or ""), str(d.get("msg") or d.get("message") or r.text[:200]))

    def resend_confirmation(self, email, redirect_to):
        self._post("/resend", {"type": "signup", "email": email}, params={"redirect_to": redirect_to})

    def send_otp(self, email):
        self._post("/otp", {"email": email, "create_user": True})

    def verify_otp(self, email, code):
        try:
            d = self._post("/verify", {"type": "email", "email": email, "token": code})
        except AuthError as e:
            if e.code in ("unknown", "invalid", "invalid_token"):
                raise AuthError("bad_code") from e
            raise
        u = d.get("user") or {}
        if not u.get("id"):
            raise AuthError("bad_code")
        return {"user_id": u["id"], "email": u.get("email", email)}


class MemoryAuth(Auth):
    """로컬·테스트용. confirm_required=True 면 확인 토큰을 outbox 에 남긴다 (메일 대신)."""

    def __init__(self, confirm_required: bool = True):
        self.users: dict[str, dict] = {}
        self.tokens: dict[str, str] = {}
        self.outbox: list[dict] = []
        self.confirm_required = confirm_required

    def _by_email(self, email):
        return next((u for u in self.users.values() if u["email"] == email.lower()), None)

    def _token(self, uid, kind="access"):
        t = f"{kind}-{secrets.token_hex(8)}"
        self.tokens[t] = uid
        return t

    def sign_up(self, email, password, redirect_to):
        if "@" not in email or "." not in email.split("@")[-1]:
            raise AuthError("bad_email")
        if len(password) < 8:
            raise AuthError("weak_password")
        if (u := self._by_email(email)) and u["confirmed"]:
            raise AuthError("exists")
        uid = u["id"] if u else f"{secrets.token_hex(4)}-0000-4000-8000-{secrets.token_hex(6)}"
        self.users[uid] = {"id": uid, "email": email.lower(), "pw": hash_pw(password),
                           "confirmed": not self.confirm_required}
        if self.confirm_required:
            self.outbox.append({"to": email.lower(), "type": "signup", "token": self._token(uid),
                                "redirect_to": redirect_to})
        return {"user_id": uid, "email": email.lower(), "confirmed": not self.confirm_required}

    def sign_in(self, email, password):
        u = self._by_email(email)
        if not u or not verify_pw(password, u["pw"]):
            raise AuthError("invalid")
        if not u["confirmed"]:
            raise AuthError("not_confirmed")
        return {"user_id": u["id"], "email": u["email"], "access_token": self._token(u["id"])}

    def user_from_token(self, access_token):
        uid = self.tokens.get(access_token)
        if not uid:
            raise AuthError("invalid_token")
        u = self.users[uid]
        u["confirmed"] = True                       # 메일의 링크를 누른 것과 같다
        return {"user_id": uid, "email": u["email"], "confirmed": True}

    def send_reset(self, email, redirect_to):
        if (u := self._by_email(email)):
            self.outbox.append({"to": u["email"], "type": "recovery", "token": self._token(u["id"]),
                                "redirect_to": redirect_to})

    def set_password(self, access_token, new_password):
        uid = self.tokens.get(access_token)
        if not uid:
            raise AuthError("invalid_token")
        self.users[uid]["pw"] = hash_pw(new_password)

    def send_otp(self, email):
        if "@" not in email:
            raise AuthError("bad_email")
        u = self._by_email(email)
        if not u:
            uid = f"{secrets.token_hex(4)}-0000-4000-8000-{secrets.token_hex(6)}"
            u = self.users[uid] = {"id": uid, "email": email.lower(), "pw": "!", "confirmed": False}
        code = f"{secrets.randbelow(10**6):06d}"
        u["otp"] = code
        self.outbox.append({"to": u["email"], "type": "otp", "token": code})

    def verify_otp(self, email, code):
        u = self._by_email(email)
        if not u or not u.get("otp") or code != u["otp"]:
            raise AuthError("bad_code")
        u["otp"], u["confirmed"] = None, True
        return {"user_id": u["id"], "email": u["email"]}

    def resend_confirmation(self, email, redirect_to):
        if (u := self._by_email(email)) and not u["confirmed"]:
            self.outbox.append({"to": u["email"], "type": "signup", "token": self._token(u["id"]),
                                "redirect_to": redirect_to})


@lru_cache(maxsize=1)
def get_auth() -> Auth:
    url, anon = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY")
    if url and anon:
        return SupabaseAuth(url, anon)
    return MemoryAuth(confirm_required=False)
