"""학습 기록 저장소.

- SupabaseStore: Supabase 의 elenchos 스키마에 저장. 테이블은 직접 노출하지 않고,
  서버만 아는 키(ELENCHOS_DB_KEY)를 확인하는 함수(RPC)로만 읽고 쓴다.
  판정·기록 쓰기가 서버에서만 일어나므로 학생이 자기 기록을 고칠 수 없다.
- MemoryStore: 로컬 개발·테스트용 (프로세스 메모리).

Vercel 함수는 요청마다 새로 뜰 수 있으므로 운영에서는 반드시 SupabaseStore 를 쓴다.
"""
import os
from functools import lru_cache

import httpx

from src.learning.state import LearnerState


class Store:
    def load(self, sid: str) -> LearnerState:
        raise NotImplementedError

    def save(self, state: LearnerState, *, is_demo: bool, name: str) -> None:
        raise NotImplementedError

    def list_students(self, include_demo: bool) -> list[dict]:
        raise NotImplementedError

    def suspended(self) -> dict[str, str]:
        raise NotImplementedError

    def set_status(self, item_id: str, status: str, note: str, by: str) -> None:
        raise NotImplementedError

    # 지도·시스템 의견 (가이드 9·14장): 학습 기록과 분리된 저장소.
    # 익명이면 계정·회차 ID·정확한 시각을 남기지 않는다 (날짜만).
    def add_feedback(self, kind: str, answers: dict, user_id: str | None) -> None:
        raise NotImplementedError

    def list_feedback(self) -> list[dict]:
        raise NotImplementedError

    # 계정·학급 (web/accounts.py 가 사용). 비밀번호는 해시만 저장한다.
    def account_by_login(self, login_id: str) -> dict | None:
        raise NotImplementedError

    def account_get(self, aid: str) -> dict | None:
        raise NotImplementedError

    def account_create(self, aid: str, login_id: str, pw_hash: str, role: str, name: str, by: str) -> None:
        raise NotImplementedError

    def account_update(self, aid: str, patch: dict) -> None:
        raise NotImplementedError

    def account_list(self, role: str | None = None) -> list[dict]:
        raise NotImplementedError

    def class_create(self, cid: str, name: str, teacher_id: str, pack_id: str) -> None:
        raise NotImplementedError

    def class_list(self, teacher_id: str | None = None) -> list[dict]:
        raise NotImplementedError

    def class_add_member(self, cid: str, student_id: str) -> None:
        raise NotImplementedError

    def audit(self, who: str, action: str, target: str = "") -> None:
        raise NotImplementedError

    # 이메일 가입 (Supabase Auth 사용자와 연결)
    def account_by_auth(self, auth_id: str) -> dict | None:
        raise NotImplementedError

    def account_create_auth(self, aid: str, auth_id: str, email: str, name: str, consent: dict) -> None:
        raise NotImplementedError

    def account_set_role(self, aid: str, role: str) -> None:
        raise NotImplementedError

    def class_set_code(self, cid: str, code: str) -> None:
        raise NotImplementedError

    def class_by_code(self, code: str) -> dict | None:
        raise NotImplementedError

    def classes_of_student(self, sid: str) -> list[dict]:
        raise NotImplementedError


class MemoryStore(Store):
    def __init__(self):
        self.states: dict[str, dict] = {}
        self.meta: dict[str, dict] = {}
        self.status: dict[str, dict] = {}
        self.feedback: list[dict] = []
        self.accounts: dict[str, dict] = {}
        self.classes: dict[str, dict] = {}
        self.members: set[tuple[str, str]] = set()
        self.audits: list[dict] = []

    def load(self, sid):
        raw = self.states.get(sid)
        return LearnerState.model_validate(raw) if raw else LearnerState(student_id=sid)

    def save(self, state, *, is_demo, name):
        self.states[state.student_id] = state.model_dump(mode="json")
        self.meta[state.student_id] = {"id": state.student_id, "display_name": name, "is_demo": is_demo}

    def list_students(self, include_demo):
        return [m for m in self.meta.values() if include_demo or not m["is_demo"]]

    def suspended(self):
        return {k: v["note"] for k, v in self.status.items() if v["status"] == "suspended"}

    def set_status(self, item_id, status, note, by):
        self.status[item_id] = {"status": status, "note": note, "by": by}

    def add_feedback(self, kind, answers, user_id):
        from datetime import date
        self.feedback.append({"kind": kind, "answers": answers, "named": user_id is not None,
                              "user_id": user_id, "day": date.today().isoformat()})

    def list_feedback(self):
        return list(self.feedback)

    def account_by_login(self, login_id):
        return next((dict(a) for a in self.accounts.values() if a["login_id"] == login_id.lower()), None)

    def account_get(self, aid):
        a = self.accounts.get(aid)
        return {k: v for k, v in a.items() if k != "pw_hash"} if a else None

    def account_create(self, aid, login_id, pw_hash, role, name, by):
        if self.account_by_login(login_id) or aid in self.accounts:
            raise RuntimeError("저장소 오류: duplicate key")
        self.accounts[aid] = {"id": aid, "login_id": login_id.lower(), "pw_hash": pw_hash, "role": role,
                              "display_name": name, "active": True, "must_change_pw": True, "consent": {},
                              "failed_logins": 0, "locked_until": None, "created_by": by, "last_login": None}

    def account_update(self, aid, patch):
        from datetime import UTC, datetime
        a = self.accounts[aid]
        for k, v in patch.items():
            a[k] = datetime.now(UTC).isoformat(timespec="seconds") if k == "last_login" else v

    def account_list(self, role=None):
        return [self.account_get(a["id"]) for a in self.accounts.values() if role is None or a["role"] == role]

    def class_create(self, cid, name, teacher_id, pack_id):
        self.classes[cid] = {"id": cid, "name": name, "teacher_id": teacher_id, "pack_id": pack_id}

    def class_list(self, teacher_id=None):
        out = []
        for c in self.classes.values():
            if teacher_id is None or c["teacher_id"] == teacher_id:
                studs = [self.account_get(s) for (k, s) in sorted(self.members) if k == c["id"]]
                out.append({**c, "students": studs})
        return out

    def class_add_member(self, cid, student_id):
        self.members.add((cid, student_id))

    def audit(self, who, action, target=""):
        self.audits.append({"who": who, "action": action, "target": target})

    def account_by_auth(self, auth_id):
        a = next((a for a in self.accounts.values() if a.get("auth_id") == auth_id), None)
        return self.account_get(a["id"]) if a else None

    def account_create_auth(self, aid, auth_id, email, name, consent):
        if self.account_by_auth(auth_id):
            return
        self.accounts[aid] = {"id": aid, "login_id": email.lower(), "email": email.lower(), "auth_id": auth_id,
                              "pw_hash": "!", "role": "student", "display_name": name, "active": True,
                              "must_change_pw": False, "consent": consent, "failed_logins": 0,
                              "locked_until": None, "created_by": "signup", "last_login": None}

    def account_set_role(self, aid, role):
        self.accounts[aid]["role"] = role

    def class_set_code(self, cid, code):
        self.classes[cid]["join_code"] = code.upper()

    def class_by_code(self, code):
        return next(({"id": c["id"], "name": c["name"], "teacher_id": c["teacher_id"]}
                     for c in self.classes.values() if c.get("join_code") == code.upper()), None)

    def classes_of_student(self, sid):
        return [{"id": k, "name": self.classes[k]["name"]} for (k, s) in self.members if s == sid]


class SupabaseStore(Store):
    def __init__(self, url: str, anon_key: str, db_key: str):
        self.url = url.rstrip("/") + "/rest/v1/rpc/"
        self.headers = {"apikey": anon_key, "Authorization": f"Bearer {anon_key}",
                        "Content-Type": "application/json"}
        self.db_key = db_key
        self.client = httpx.Client(timeout=10)

    def _rpc(self, fn: str, **params):
        r = self.client.post(self.url + fn, headers=self.headers, json={"p_key": self.db_key, **params})
        if r.status_code >= 400:
            raise RuntimeError(f"저장소 오류 {fn}: {r.status_code} {r.text[:200]}")
        return r.json() if r.content else None

    def load(self, sid):
        raw = self._rpc("elenchos_get_state", p_id=sid)
        return LearnerState.model_validate(raw) if raw else LearnerState(student_id=sid)

    def save(self, state, *, is_demo, name):
        self._rpc("elenchos_put_state", p_id=state.student_id, p_state=state.model_dump(mode="json"),
                  p_is_demo=is_demo, p_name=name)

    def list_students(self, include_demo):
        return self._rpc("elenchos_list_states", p_include_demo=include_demo) or []

    def suspended(self):
        return self._rpc("elenchos_get_suspended") or {}

    def set_status(self, item_id, status, note, by):
        self._rpc("elenchos_set_status", p_item=item_id, p_status=status, p_note=note, p_by=by)

    def add_feedback(self, kind, answers, user_id):
        self._rpc("elenchos_add_feedback", p_kind=kind, p_answers=answers, p_user=user_id)

    def list_feedback(self):
        return self._rpc("elenchos_list_feedback") or []

    def account_by_login(self, login_id):
        return self._rpc("elenchos_account_by_login", p_login=login_id)

    def account_get(self, aid):
        return self._rpc("elenchos_account_get", p_id=aid)

    def account_create(self, aid, login_id, pw_hash, role, name, by):
        self._rpc("elenchos_account_create", p_id=aid, p_login=login_id, p_hash=pw_hash, p_role=role,
                  p_name=name, p_by=by)

    def account_update(self, aid, patch):
        self._rpc("elenchos_account_update", p_id=aid, p_patch=patch)

    def account_list(self, role=None):
        return self._rpc("elenchos_account_list", p_role=role) or []

    def class_create(self, cid, name, teacher_id, pack_id):
        self._rpc("elenchos_class_create", p_id=cid, p_name=name, p_teacher=teacher_id, p_pack=pack_id)

    def class_list(self, teacher_id=None):
        return self._rpc("elenchos_class_list", p_teacher=teacher_id) or []

    def class_add_member(self, cid, student_id):
        self._rpc("elenchos_class_add_member", p_class=cid, p_student=student_id)

    def audit(self, who, action, target=""):
        self._rpc("elenchos_audit", p_who=who, p_action=action, p_target=target)

    def account_by_auth(self, auth_id):
        return self._rpc("elenchos_account_by_auth", p_auth=auth_id)

    def account_create_auth(self, aid, auth_id, email, name, consent):
        self._rpc("elenchos_account_create_auth", p_id=aid, p_auth=auth_id, p_email=email, p_name=name,
                  p_consent=consent)

    def account_set_role(self, aid, role):
        self._rpc("elenchos_account_set_role", p_id=aid, p_role=role)

    def class_set_code(self, cid, code):
        self._rpc("elenchos_class_set_code", p_id=cid, p_code=code)

    def class_by_code(self, code):
        return self._rpc("elenchos_class_by_code", p_code=code)

    def classes_of_student(self, sid):
        return self._rpc("elenchos_classes_of_student", p_student=sid) or []


@lru_cache(maxsize=1)
def get_store() -> Store:
    url, anon, key = (os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY"), os.getenv("ELENCHOS_DB_KEY"))
    if url and anon and key:
        return SupabaseStore(url, anon, key)
    return MemoryStore()
