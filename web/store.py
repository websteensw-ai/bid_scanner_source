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


class MemoryStore(Store):
    def __init__(self):
        self.states: dict[str, dict] = {}
        self.meta: dict[str, dict] = {}
        self.status: dict[str, dict] = {}

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


@lru_cache(maxsize=1)
def get_store() -> Store:
    url, anon, key = (os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY"), os.getenv("ELENCHOS_DB_KEY"))
    if url and anon and key:
        return SupabaseStore(url, anon, key)
    return MemoryStore()
