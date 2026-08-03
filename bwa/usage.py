"""Per-user daily run limit.

One blog run makes 8-12 Groq calls, so on a shared deployment a single
enthusiastic visitor can exhaust the owner's free tier before lunch. This keeps
a per-email counter that resets at UTC midnight.

The counter lives in a ``@st.cache_resource`` singleton, which is shared across
every session in the server process. That is the right scope for a single
Community Cloud instance. It is deliberately in memory: a restart clears the
counters, which is an acceptable trade for having no database.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import streamlit as st


@dataclass
class Quota:
    used: int
    limit: Optional[int]     # None = unlimited

    @property
    def unlimited(self) -> bool:
        return self.limit is None

    @property
    def remaining(self) -> int:
        if self.limit is None:
            return 10**9
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        return not self.unlimited and self.remaining <= 0

    def describe(self) -> str:
        if self.unlimited:
            return f"{self.used} run(s) today · no limit"
        return f"{self.remaining} of {self.limit} runs left today"


class _Counter:
    """Thread-safe {(email, utc_date): count}."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: Dict[Tuple[str, str], int] = {}

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _prune(self, today: str) -> None:
        stale = [k for k in self._counts if k[1] != today]
        for key in stale:
            del self._counts[key]

    def get(self, email: str) -> int:
        today = self._today()
        with self._lock:
            self._prune(today)
            return self._counts.get((email, today), 0)

    def increment(self, email: str) -> int:
        today = self._today()
        with self._lock:
            self._prune(today)
            key = (email, today)
            self._counts[key] = self._counts.get(key, 0) + 1
            return self._counts[key]

    def snapshot(self) -> Dict[str, int]:
        today = self._today()
        with self._lock:
            return {e: c for (e, d), c in self._counts.items() if d == today}


@st.cache_resource(show_spinner=False)
def _counter() -> _Counter:
    return _Counter()


def quota_for(email: str, limit: Optional[int]) -> Quota:
    if not email:
        return Quota(used=0, limit=limit)
    return Quota(used=_counter().get(email), limit=limit)


def record_run(email: str) -> None:
    """Call once a generation has actually started."""
    if email:
        _counter().increment(email)


def all_usage_today() -> Dict[str, int]:
    """Admin view: {email: runs} for the current UTC day."""
    return _counter().snapshot()
