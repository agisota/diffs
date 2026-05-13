"""Optional HTTP Basic Auth — gated by BASIC_AUTH_USER + BASIC_AUTH_PASS env.

When both env vars set, every request except /health and /static/* is
challenged. When either is empty/missing, app stays anonymous (default).
"""

from __future__ import annotations

import base64
import hmac
import os
from typing import Awaitable, Callable

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware


# Paths that NEVER require auth (probes, static assets, OpenAPI for ops).
_PUBLIC_PATHS = ("/health", "/static/", "/openapi.json", "/docs", "/redoc")


def _is_public(path: str) -> bool:
    if path == "/health":
        return True
    for p in _PUBLIC_PATHS:
        if path.startswith(p):
            return True
    return False


def _expected_creds() -> tuple[str, str] | None:
    user = os.getenv("BASIC_AUTH_USER", "").strip()
    password = os.getenv("BASIC_AUTH_PASS", "").strip()
    if user and password:
        return (user, password)
    return None


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Constant-time-compare HTTP Basic Auth, optional via env."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        creds = _expected_creds()
        if creds is None or _is_public(request.url.path):
            return await call_next(request)

        header = request.headers.get("authorization", "")
        if not header.lower().startswith("basic "):
            return _unauthorized()
        try:
            decoded = base64.b64decode(header[6:].strip()).decode("utf-8", errors="replace")
        except Exception:
            return _unauthorized()
        if ":" not in decoded:
            return _unauthorized()
        user, _, password = decoded.partition(":")
        exp_user, exp_pass = creds
        # Constant-time compare both halves to prevent timing leaks.
        u_ok = hmac.compare_digest(user.encode("utf-8"), exp_user.encode("utf-8"))
        p_ok = hmac.compare_digest(password.encode("utf-8"), exp_pass.encode("utf-8"))
        if u_ok and p_ok:
            return await call_next(request)
        return _unauthorized()


def _unauthorized() -> Response:
    return Response(
        content="Authentication required",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="DocDiffOps", charset="UTF-8"'},
    )
