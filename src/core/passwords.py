"""비밀번호 해시 (PBKDF2-SHA256, 무작위 salt). 웹 계층과 독립적이라 관리 스크립트에서도 쓴다."""
import hashlib
import hmac
import secrets

ITERATIONS = 200_000
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"     # 헷갈리는 글자(0 o 1 l i) 제외


def hash_pw(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt}${dk.hex()}"


def verify_pw(pw: str, stored: str) -> bool:
    try:
        algo, it, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), digest)
    except (ValueError, TypeError):
        return False


def new_password(n: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def pw_problem(pw: str, login_id: str = "") -> str | None:
    if len(pw) < 8:
        return "비밀번호는 8자 이상이어야 해요."
    if pw.lower() == login_id.lower() or pw.isdigit() or len(set(pw)) < 4:
        return "추측하기 쉬운 비밀번호예요. 다른 비밀번호를 써 주세요."
    return None
