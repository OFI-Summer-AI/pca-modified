import time
from threading import Lock

_TTL = 3600  # 1 hour


class _SessionStore:
    def __init__(self):
        self._store: dict = {}
        self._lock = Lock()

    def set(self, session_id: str, data: dict) -> None:
        with self._lock:
            self._store[session_id] = {"data": data, "expires": time.time() + _TTL}
        self._cleanup()

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            entry = self._store.get(session_id)
            if not entry:
                return None
            if entry["expires"] < time.time():
                del self._store[session_id]
                return None
            return entry["data"]

    def _cleanup(self) -> None:
        now = time.time()
        with self._lock:
            expired = [k for k, v in self._store.items() if v["expires"] < now]
            for k in expired:
                del self._store[k]


store = _SessionStore()
