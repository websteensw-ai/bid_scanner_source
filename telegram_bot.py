"""텔레그램 봇 연동 (계정 연결 + 알림 발송).

텔레그램은 봇이 사용자에게 먼저 말을 걸 수 없으므로(스팸 방지 정책), 사용자가 딥링크
(t.me/<bot>?start=<code>)를 눌러 봇과 대화를 시작해야 chat_id를 얻을 수 있다.
로컬 개발 환경(공인 도메인 없음)이라 웹훅 대신, getUpdates를 주기적으로 폴링하는 방식을 쓴다.
"""
import os
import time
import threading
import uuid
import requests

_PLACEHOLDER_VALUES = {"your_telegram_bot_token_here", "your_bot_username_here", ""}

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

_pending_links = {}   # code -> {user_id, access_token, refresh_token}
_linked_results = {}  # user_id -> chat_id (연동 직후, 세션에 반영되기 전까지 잠깐 보관)
_lock = threading.Lock()
_link_callback = None  # app.py가 등록: fn(user_id, access_token, refresh_token, chat_id)


def is_configured() -> bool:
    return BOT_TOKEN not in _PLACEHOLDER_VALUES and BOT_USERNAME not in _PLACEHOLDER_VALUES


def set_link_callback(fn) -> None:
    global _link_callback
    _link_callback = fn


def create_link_code(user_id: str, access_token: str, refresh_token: str) -> str:
    code = uuid.uuid4().hex[:16]
    with _lock:
        _pending_links[code] = {
            "user_id": user_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
    return code


def get_connect_url(code: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start={code}"


def check_and_consume_link(user_id: str):
    """이 user_id가 방금 연동됐는지 확인하고, 있으면 chat_id를 반환 후 제거한다."""
    with _lock:
        return _linked_results.pop(user_id, None)


def send_message(chat_id: str, text: str) -> bool:
    if not is_configured() or not chat_id:
        return False
    try:
        resp = requests.post(
            f"{API_BASE}/sendMessage",
            data={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=10,
        )
        return resp.ok
    except Exception as e:
        print(f"[Warn] 텔레그램 메시지 발송 실패: {e}")
        return False


def _handle_start(chat_id, code: str) -> None:
    with _lock:
        pending = _pending_links.pop(code, None)
    if not pending:
        send_message(str(chat_id), "연결 코드가 만료되었거나 올바르지 않습니다. 웹사이트에서 다시 시도해주세요.")
        return

    if _link_callback:
        try:
            _link_callback(pending["user_id"], pending["access_token"], pending["refresh_token"], str(chat_id))
        except Exception as e:
            print(f"[Warn] 텔레그램 연동 콜백 실패: {e}")

    with _lock:
        _linked_results[pending["user_id"]] = str(chat_id)

    send_message(str(chat_id), "✅ 텔레그램 연결이 완료되었습니다. 분석이 끝나면 여기로 알려드릴게요.")


def _poll_loop() -> None:
    offset = 0
    while True:
        try:
            resp = requests.get(f"{API_BASE}/getUpdates", params={"offset": offset, "timeout": 20}, timeout=25)
            data = resp.json()
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message") or {}
                text = message.get("text", "")
                chat_id = (message.get("chat") or {}).get("id")
                if chat_id and text.startswith("/start"):
                    parts = text.split(" ", 1)
                    code = parts[1].strip() if len(parts) > 1 else ""
                    if code:
                        _handle_start(chat_id, code)
                    else:
                        send_message(str(chat_id), "웹사이트의 '텔레그램 연결하기' 버튼을 통해 접속해주세요.")
        except Exception as e:
            print(f"[Warn] 텔레그램 polling 오류: {e}")
            time.sleep(5)


def start_polling() -> None:
    if not is_configured():
        print("[Info] TELEGRAM_BOT_TOKEN/TELEGRAM_BOT_USERNAME이 설정되지 않아 텔레그램 연동을 비활성화합니다.")
        return
    threading.Thread(target=_poll_loop, daemon=True).start()
    print(f"[Info] 텔레그램 봇 폴링 시작 (@{BOT_USERNAME})")
