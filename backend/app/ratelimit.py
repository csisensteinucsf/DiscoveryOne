import os, time, re
import logging
from collections import defaultdict
from typing import Optional, Sequence, Tuple, List, Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

try:
    import redis.asyncio as redis
except Exception:
    redis = None

from .middleware import _remote_ip

_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"hits": 0, "blocked": 0})
logger = logging.getLogger(__name__)


def load_rules_from_env(defaults: Optional[Sequence[Tuple[str, str, int, int]]] = None) -> List[Tuple[str, str, int, int]]:
    """
    Parse RATE_LIMIT_RULES env when present.
    Format: "pattern|METHOD|limit|window;pattern2|*|limit|window"
    Example: r'^/api/auth/token$'|POST|10|60;^/api/cases|POST|60|60
    Falls back to provided defaults when unset or invalid.
    """
    raw = os.getenv("RATE_LIMIT_RULES", "").strip()
    if not raw:
        return list(defaults or [])
    rules: List[Tuple[str, str, int, int]] = []
    for part in re.split(r"[;,\n]+", raw):
        chunk = part.strip()
        if not chunk:
            continue
        pieces = chunk.split("|")
        if len(pieces) != 4:
            continue
        pattern, method, lim, win = pieces
        try:
            rules.append((pattern, method.upper(), int(lim), int(win)))
        except ValueError:
            continue
    if not rules and defaults:
        return list(defaults)
    return rules


def rate_limit_stats(rules: Sequence[Tuple[str, str, int, int]], redis_url: Optional[str]) -> List[Dict[str, Any]]:
    data: List[Dict[str, Any]] = []
    for pattern, method, limit, window in rules:
        key = f"{pattern}:{method}"
        counters = _stats.get(key, {"hits": 0, "blocked": 0})
        data.append(
            {
                "pattern": pattern,
                "method": method,
                "limit": limit,
                "window": window,
                "hits": counters.get("hits", 0),
                "blocked": counters.get("blocked", 0),
                "backend": "redis" if redis_url else "memory",
            }
        )
    return data


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rules: Optional[Sequence[Tuple[str,str,int,int]]] = None, redis_url: Optional[str]=None):
        super().__init__(app)
        self.rules = [(re.compile(p), m.upper(), lim, win) for p,m,lim,win in (rules or [])]
        self.client = None
        self.redis_url = redis_url or os.getenv('REDIS_URL')
        self._rules_config = rules or []
        self._redis_failed = False
        if not self.redis_url or redis is None:
            logger.warning("Rate limiting using in-memory counters; configure REDIS_URL for multi-worker enforcement.")

    async def dispatch(self, request: Request, call_next):
        if not self.rules:
            return await call_next(request)
        method = request.method.upper()
        path = request.url.path
        ip = _remote_ip(request)
        for pat, m, limit, window in self.rules:
            if (m == '*' or m == method) and pat.match(path):
                key = f"{pat.pattern}:{m}"
                allowed = await self._allow(ip, key, limit, window)
                stats_key = f"{pat.pattern}:{m}"
                _stats[stats_key]["hits"] += 1
                if not allowed:
                    _stats[stats_key]["blocked"] += 1
                    return JSONResponse({'detail':'rate_limited'}, status_code=429)
        return await call_next(request)

    async def _allow(self, ip: str, bucket: str, limit: int, window: int) -> bool:
        key = f'rl:{ip}:{bucket}:{window}'
        if self.redis_url and redis is not None:
            try:
                if self.client is None:
                    self.client = redis.from_url(self.redis_url, encoding='utf-8', decode_responses=True)
                pipe = self.client.pipeline(True)
                pipe.incr(key)
                pipe.expire(key, window)
                count, _ = await pipe.execute()
                return int(count) <= limit
            except Exception:
                if not self._redis_failed:
                    logger.warning("Rate limiting falling back to in-memory counters (Redis unavailable).")
                    self._redis_failed = True
        # in-memory fallback (per-process only)
        now = int(time.time())
        wnd = now - (now % window)
        store = getattr(self, '_mem', {})
        self._mem = store
        bucket_store = store.setdefault(key, {})
        # prune stale windows
        for past in list(bucket_store.keys()):
            if past != wnd and past < wnd:
                bucket_store.pop(past, None)
        bucket_store[wnd] = bucket_store.get(wnd, 0) + 1
        return bucket_store[wnd] <= limit
