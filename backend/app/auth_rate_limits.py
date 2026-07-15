import time
import threading
from collections import defaultdict, deque

from fastapi import HTTPException


class TokenAttemptLimiter:
    def __init__(self):
        self._store: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, *, window: int, limit: int) -> tuple[bool, int]:
        if limit <= 0:
            return True, 0
        now = time.time()
        with self._lock:
            bucket = self._store[key]
            while bucket and now - bucket[0] >= window:
                bucket.popleft()
            if len(bucket) >= limit:
                retry = max(1, int(window - (now - bucket[0])))
                return False, retry
            bucket.append(now)
            return True, 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


def enforce_token_attempt_limit(limiter: TokenAttemptLimiter, key: str, *, window: int, limit: int, detail: str):
    allowed, retry = limiter.allow(key, window=window, limit=limit)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=detail,
            headers={"Retry-After": str(retry)},
        )