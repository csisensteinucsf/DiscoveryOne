# backend/app/mw_login_audit.py
import os
import jwt
from jwt import InvalidTokenError as JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import func
from .audit import log_event
from .database import SessionLocal
from . import models
from .safe_log import debug_suppressed as _debug_suppressed

def _extract_cookie_token(set_cookie_value: str, name: str = "access_token") -> str | None:
    if not set_cookie_value:
        return None
    key = name + "="
    idx = set_cookie_value.find(key)
    if idx == -1:
        return None
    start = idx + len(key)
    end = set_cookie_value.find(";", start)
    return set_cookie_value[start:] if end == -1 else set_cookie_value[start:end]

class LoginAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)

        try:
            # Only watch token endpoint successes
            if request.method == "POST" and request.url.path.endswith("/token") and response.status_code == 200:
                set_cookie = response.headers.get("set-cookie") or response.headers.get("Set-Cookie")
                token = _extract_cookie_token(set_cookie, "access_token")

                username = None
                if token:
                    try:
                        pub = (os.getenv("JWT_PUBLIC_KEY") or "").replace("\\n", "\n").strip()
                        secret = os.getenv("SECRET_KEY", "")
                        alg = (os.getenv("ALGORITHM", "HS256") or "HS256").upper()
                        if pub:
                            try:
                                payload = jwt.decode(token, pub, algorithms=["RS256"])
                            except JWTError:
                                payload = jwt.decode(token, secret, algorithms=[alg]) if secret else {}
                        else:
                            payload = jwt.decode(token, secret, algorithms=[alg]) if secret else {}
                        username = payload.get("sub")
                    except JWTError:
                        username = None

                db = SessionLocal()
                try:
                    user = None
                    if username:
                        user = db.query(models.User).filter(func.lower(models.User.username) == username.lower()).first()

                    ip = getattr(getattr(request, "client", None), "host", None)
                    ua = request.headers.get("user-agent")

                    msg = f"Successful login for {username or (user.username if user else '?')} from {ip or '-'} ({(ua or '-')[:120]})"
                    # Primary
                    actor_id = user.id if user else None
                    log_event(
                        db,
                        action="login_success",
                        target_type="user",
                        target_id=actor_id,
                        actor_id=actor_id,
                        details={"message": msg},
                        request=request,
                    )
                    # Legacy alias (if UI filters on this)
                    log_event(
                        db,
                        action="auth_login_success",
                        target_type="user",
                        target_id=actor_id,
                        actor_id=actor_id,
                        details={"message": msg},
                        request=request,
                    )
                finally:
                    try:
                        db.close()
                    except Exception as exc:
                        _debug_suppressed("suppressed exception in mw_login_audit.py:83", exc)
        except Exception as exc:
            # Never block auth if logging fails
            _debug_suppressed("suppressed exception in mw_login_audit.py:85", exc)

        return response

