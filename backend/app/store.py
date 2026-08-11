"""Very small in-memory session store.

One process, no persistence, no auth — good enough for a local/dev
deployment where a person uploads their own file and works with it in
one sitting. Each uploaded dataset gets a session_id; expensive results
(model training) are cached per session+params so re-rendering a screen
doesn't retrain from scratch.

If this ever needs to run for multiple concurrent users in production,
swap this for Redis or a proper job queue — the interface (get/set) is
small on purpose so that swap is easy.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import pandas as pd


@dataclass
class Session:
    raw_df: pd.DataFrame
    filename: str
    cache: Dict[str, Any] = field(default_factory=dict)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, raw_df: pd.DataFrame, filename: str) -> str:
        session_id = uuid.uuid4().hex
        with self._lock:
            self._sessions[session_id] = Session(raw_df=raw_df, filename=filename)
        return session_id

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def cache_get(self, session_id: str, key: str) -> Any:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return session.cache.get(key)

    def cache_set(self, session_id: str, key: str, value: Any) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            session.cache[key] = value

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None


store = SessionStore()
