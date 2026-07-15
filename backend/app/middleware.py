import os
import secrets
import time
import uuid
from collections import defaultdict
from typing import Dict, Iterable, Optional, Union
import hmac
import ipaddress

from starlette import status as _status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from .safe_log import debug_suppressed as _debug_suppressed

try:
    import redis.asyncio as redis
except Exception:
    redis = None

_TRUST_PROXY_HEADERS = (os.getenv("TRUST_PROXY_HEADERS") or "").strip().lower() in {"1", "true", "yes", "on"}
_TRUSTED_PROXY_VALUES = [
    part.strip()
    for part in (os.getenv("TRUSTED_PROXY_IPS") or "").split(",")
    if part.strip()
]
_TRUST_PROXY_XFF_MODE = (os.getenv("TRUST_PROXY_XFF_MODE") or "rightmost_untrusted").strip().lower()
_TRUST_PROXY_ALLOW_ALL = any(value == "*" for value in _TRUSTED_PROXY_VALUES)
_TRUSTED_PROXY_HOSTS: set[str] = set()
_IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]
_TRUSTED_PROXY_NETWORKS: list[_IPNetwork] = []
for value in _TRUSTED_PROXY_VALUES:
    if value == "*":
        continue
    try:
        _TRUSTED_PROXY_NETWORKS.append(ipaddress.ip_network(value, strict=False))
        continue
    except ValueError:
        pass
    _TRUSTED_PROXY_HOSTS.add(value)
def _parse_forwarded_for(header_value: Optional[str]) -> list[str]:
    if not header_value:
        return []
    values: list[str] = []
    for part in header_value.split(","):
        token = (part or "").strip()
        if not token or token.lower() == "unknown":
            continue
        host = token
        if host.startswith("[") and "]" in host:
            host = host[1 : host.index("]")]
        elif host.count(":") == 1:
            maybe_host, maybe_port = host.split(":", 1)
            if maybe_port.isdigit():
                host = maybe_host
        try:
            ipaddress.ip_address(host)
        except ValueError:
            continue
        values.append(host)
    return values


def _is_trusted_proxy_ip(addr: ipaddress._BaseAddress) -> bool:  # type: ignore[attr-defined]
    if _TRUST_PROXY_ALLOW_ALL:
        return True
    if str(addr).lower() in _TRUSTED_PROXY_HOSTS:
        return True
    for network in _TRUSTED_PROXY_NETWORKS:
        try:
            if addr in network:
                return True
        except TypeError:
            continue
    return False

def _trusted_proxy_supplied(request: Request) -> bool:
    if not _TRUST_PROXY_HEADERS or request is None:
        return False
    client = getattr(request, "client", None)
    host = getattr(client, "host", None)
    if not host:
        return False
    if _TRUST_PROXY_ALLOW_ALL:
        return True
    host_lower = host.lower()
    if host_lower in _TRUSTED_PROXY_HOSTS:
        return True
    try:
        addr = ipaddress.ip_address(host)
        for network in _TRUSTED_PROXY_NETWORKS:
            if addr in network:
                return True
    except ValueError:
        return False
    return False

def _remote_ip(request) -> str:
    if request is None:
        return "unknown"
    if _trusted_proxy_supplied(request):
        xff = _parse_forwarded_for(request.headers.get("x-forwarded-for"))
        if not xff:
            xff = _parse_forwarded_for(request.headers.get("x-real-ip"))

        if xff:
            if _TRUST_PROXY_XFF_MODE in {"first", "legacy_first"}:
                return xff[0]

            client_host = getattr(getattr(request, "client", None), "host", None)
            try:
                downstream = ipaddress.ip_address(client_host) if client_host else None
            except ValueError:
                downstream = None

            addrs: list[ipaddress._BaseAddress] = []  # type: ignore[attr-defined]
            for ip in xff:
                try:
                    addrs.append(ipaddress.ip_address(ip))
                except ValueError:
                    continue
            if downstream is not None:
                addrs.append(downstream)

            if addrs:
                idx = len(addrs) - 1
                while idx >= 0 and _is_trusted_proxy_ip(addrs[idx]):
                    idx -= 1
                if idx >= 0:
                    return str(addrs[idx])
                return str(addrs[0])
    client = request.client
    return client.host if client else "unknown"

class _SharedRateLimiter:
    def __init__(self, bucket_prefix: str):
        self.bucket_prefix = bucket_prefix
        self.redis_url = os.getenv("RATE_LIMIT_REDIS_URL") or os.getenv("REDIS_URL")
        self._client = None
        self._local: Dict[str, Dict[int, int]] = defaultdict(dict)

    async def allow(self, key: str, *, window: int, limit: int) -> tuple[bool, int]:
        now = time.time()
        bucket = int(now // window)
        ttl = int(window - (now % window)) or window
        if self.redis_url and redis is not None:
            if self._client is None:
                self._client = redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
            bucket_key = f"rl:{self.bucket_prefix}:{key}:{bucket}"
            try:
                pipe = self._client.pipeline(True)
                pipe.incr(bucket_key)
                pipe.expire(bucket_key, window)
                count, _ = await pipe.execute()
                return int(count) <= limit, max(1, ttl)
            except Exception as exc:
                # fall back to local buckets if Redis is unavailable
                _debug_suppressed("suppressed exception in middleware.py:155", exc)

        store = self._local.setdefault(key, {})
        count = store.get(bucket, 0) + 1
        store[bucket] = count
        for old in list(store.keys()):
            if old != bucket:
                store.pop(old, None)
        return count <= limit, max(1, ttl)

class AuthTokenRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiter for POST /api/auth/token.
    Keys by remote IP (X-Forwarded-For first, else client host).
    Env:
      AUTH_RATE_LIMIT (int): allowed requests per window (default 10)
      AUTH_RATE_WINDOW (int): window seconds (default 60)
    """
    def __init__(self, app):
        super().__init__(app)
        self.window = int(os.getenv("AUTH_RATE_WINDOW", "60"))
        self.limit = int(os.getenv("AUTH_RATE_LIMIT", "10"))
        self.shared = _SharedRateLimiter("auth")

    async def dispatch(self, request, call_next):
        path = request.url.path
        if request.method == "POST" and path.endswith("/api/auth/token"):
            key = _remote_ip(request)
            allowed, retry = await self.shared.allow(key, window=self.window, limit=self.limit)
            if not allowed:
                return JSONResponse(
                    {"detail": "Too Many Requests"},
                    status_code=429,
                    headers={
                        "Retry-After": str(retry),
                        "X-RateLimit-Limit": str(self.limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Window": str(self.window),
                    },
                )
        return await call_next(request)

class ExpensiveEndpointRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limits high-cost endpoints (reports, logo uploads, etc.).
    Configure via:
      EXPENSIVE_RATE_LIMIT   (default 30 requests)
      EXPENSIVE_RATE_WINDOW  (default 60 seconds)
      EXPENSIVE_RATE_PATHS   (comma list of path prefixes, default "/api/reports,/api/system/logos")
      EXPENSIVE_RATE_METHODS (comma list of HTTP methods, default "GET,POST")
    """
    def __init__(self, app):
        super().__init__(app)
        self.window = int(os.getenv("EXPENSIVE_RATE_WINDOW", "60"))
        self.limit = int(os.getenv("EXPENSIVE_RATE_LIMIT", "30"))
        raw_paths = os.getenv("EXPENSIVE_RATE_PATHS", "/api/reports,/api/system/logos")
        self.paths = tuple(p.strip() for p in raw_paths.split(",") if p.strip())
        raw_methods = os.getenv("EXPENSIVE_RATE_METHODS", "GET,POST")
        self.methods = tuple(m.strip().upper() for m in raw_methods.split(",") if m.strip())
        self.shared = _SharedRateLimiter("expensive")

    async def dispatch(self, request, call_next):
        if not self.paths or not self.methods:
            return await call_next(request)
        path = request.url.path
        method = request.method.upper()
        if method not in self.methods or not any(path.startswith(prefix) for prefix in self.paths):
            return await call_next(request)
        key = f"{_remote_ip(request)}:{method}"
        allowed, retry = await self.shared.allow(key, window=self.window, limit=self.limit)
        if not allowed:
            return JSONResponse(
                {"detail": "Too Many Requests"},
                status_code=429,
                headers={
                    "Retry-After": str(retry),
                    "X-RateLimit-Limit": str(self.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Window": str(self.window),
                },
            )
        return await call_next(request)

SAFE_METHODS = {"GET","HEAD","OPTIONS"}

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        cookie_name: str = "csrf",
        header_name: str = "X-CSRF-Token",
        session_cookie: str = "access_token",
        required_methods: Iterable[str] | None = None,
        skip_paths=None,
    ):
        super().__init__(app)
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.session_cookie = session_cookie
        self.required_methods = {m.upper() for m in (required_methods or {"POST", "PUT", "PATCH", "DELETE"})}
        self.skip_paths = set(skip_paths or [])

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()
        has_session = bool(request.cookies.get(self.session_cookie))
        enforce = (
            has_session
            and method in self.required_methods
            and path not in self.skip_paths
        )
        if enforce:
            cookie = request.cookies.get(self.cookie_name)
            header = request.headers.get(self.header_name)
            if not cookie or not header or not hmac.compare_digest(cookie, header):
                return Response(status_code=_status.HTTP_403_FORBIDDEN)
        response = await call_next(request)
        if self.cookie_name not in request.cookies:
            token = secrets.token_urlsafe(32)
            response.set_cookie(
                self.cookie_name,
                token,
                httponly=False,
                secure=True,
                samesite=os.getenv("COOKIE_SAMESITE", "Strict"),
                path="/",
            )
        return response



# --- Appended by Code Copilot (request size limit) ---
class _RequestTooLarge(Exception):
    pass


class RequestSizeLimitMiddleware:
    def __init__(self, app, max_bytes: int = int(os.getenv("MAX_REQUEST_BYTES", str(10 * 1024 * 1024)))):
        self.app = app
        self.max_bytes = max_bytes
        # Case import uploads are intentionally larger than the global default.
        case_import_limit = int(
            os.getenv(
                "MAX_REQUEST_BYTES_CASE_IMPORT",
                os.getenv("CASE_IMPORT_TOTAL_MAX_BYTES", os.getenv("CASE_IMPORT_MAX_BYTES", str(max_bytes))),
            )
        )
        self.case_import_max_bytes = case_import_limit if case_import_limit > 0 else max_bytes

    def _effective_limit(self, scope) -> int:
        path = str(scope.get("path") or "")
        method = str(scope.get("method") or "").upper()
        if method == "POST" and path == "/api/system/import":
            return self.case_import_max_bytes
        return self.max_bytes

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        limit = self._effective_limit(scope)
        if limit <= 0:
            await self.app(scope, receive, send)
            return

        try:
            content_length = None
            for name, value in (scope.get("headers") or []):
                if name.lower() == b"content-length":
                    content_length = int(value.decode("latin-1"))
                    break
            if content_length is not None and content_length > limit:
                response = JSONResponse({"detail": "request_too_large"}, status_code=413)
                await response(scope, receive, send)
                return
        except Exception as exc:
            _debug_suppressed("suppressed exception in middleware.py:341", exc)

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                received += len(body)
                if received > limit:
                    raise _RequestTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestTooLarge:
            response = JSONResponse({"detail": "request_too_large"}, status_code=413)
            await response(scope, receive, send)

