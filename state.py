"""
state.py — Async, versioned, idempotent context store for Vera v4.

Tracks per-scope counts so /v1/healthz can report:
  contexts_loaded: {category: 5, merchant: 50, customer: 200, trigger: 100}
"""
import asyncio
from datetime import datetime


class StateStore:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._store: dict[tuple[str, str], dict] = {}
        self._versions: dict[tuple[str, str], int] = {}
        self._conversations: dict[str, list] = {}
        self._ack_counter: dict[str, int] = {}
        self._ack_ids: dict[tuple[str, str], str] = {}

    async def upsert(self, scope: str, context_id: str, version: int, payload: dict):
        key = (scope, context_id)
        async with self._lock:
            current_version = self._versions.get(key, 0)
            if version < current_version:
                return False, self._ack_ids.get(key)
            if version == current_version:
                return True, self._ack_ids.get(key)
            self._store[key] = payload
            self._versions[key] = version
            n = self._ack_counter.get(context_id, 0) + 1
            self._ack_counter[context_id] = n
            ack_id = f"ack_{scope}_{context_id}_{n}"
            self._ack_ids[key] = ack_id
            return True, ack_id

    def get(self, scope: str, context_id: str) -> dict | None:
        return self._store.get((scope, context_id))

    def get_version(self, scope: str, context_id: str) -> int:
        return self._versions.get((scope, context_id), 0)

    def dump_stats(self) -> dict:
        by_scope: dict[str, int] = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        for (scope, _) in self._store:
            by_scope[scope] = by_scope.get(scope, 0) + 1
        return {
            "total_contexts": len(self._store),
            "by_scope": by_scope,
            "active_sessions": len(self._conversations),
        }

    async def append_conversation(self, session_id: str, role: str, content: str):
        async with self._lock:
            if session_id not in self._conversations:
                self._conversations[session_id] = []
            self._conversations[session_id].append({
                "role": role,
                "content": content,
                "ts": datetime.utcnow().isoformat() + "Z",
            })

    def get_conversation(self, session_id: str) -> list:
        return self._conversations.get(session_id, [])
