"""Sliding-window per-IP rate limiting backed by Redis INCR+EXPIRE.

Limits (per IP, per minute):
- POST /events/{id}/review: 60/min (interactive review)
- POST /events/{id}/ai-suggest: 10/min (LLM cost)
- POST /batches: 30/min (batch creation)

Off when RATE_LIMIT_DISABLED=true or Redis unavailable.
Returns 429 with Retry-After when exceeded.
"""

from __future__ import annotations

import logging
import os
import re
import time as _t
from typing import Awaitable, Callable

import redis
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .settings import REDIS_URL

logger = logging.getLogger(__name__)

# [pattern, method, limit_per_min]
_RULES = [
    (re.compile(r"^/events/[^/]+/review$"), "POST", 60),
    (re.compile(r"^/events/[^/]+/ai-suggest$"), "POST", 10),
    (re.compile(r"^/batches$"), "POST", 30),
]

_DISABLED = os.getenv("RATE_LIMIT_DISABLED", "false").lower() == "true"

_client: redis.Redis | None = None  # type: ignore[type-arg]


def _get_client() -> redis.Redis | None:  # type: ignore[type-arg]
    global _client
    if _client is not None:
        return _client
    try:
        c = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=1.0)
        c.ping()
        _client = c
        return c
    except Exception as e:
        logger.warning("rate_limit: Redis unavailable, disabling: %s", e)
        return None


def _client_ip(request: Request) -> str:
    # Behind Caddy + Cloudflare: CF-Connecting-IP first, then X-Forwarded-For
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _match_rule(method: str, path: str) -> tuple[re.Pattern[str], int] | None:
    for pat, m, limit in _RULES:
        if m == method and pat.match(path):
            return (pat, limit)
    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if _DISABLED:
            return await call_next(request)
        rule = _match_rule(request.method, request.url.path)
        if rule is None:
            return await call_next(request)
        client = _get_client()
        if client is None:
            return await call_next(request)
        _pat, limit = rule
        ip = _client_ip(request)
        # Minute-bucket key — automatically rolls over per minute window.
        bucket = int(_t.time() // 60)
        key = f"rl:{bucket}:{_pat.pattern}:{ip}"
        try:
            n = client.incr(key)
            if n == 1:
                client.expire(key, 70)  # bucket lifetime > minute
            if n > limit:
                retry_after = 60 - (int(_t.time()) % 60)
                return JSONResponse(
                    {"detail": f"rate limit exceeded ({limit}/min)", "retry_after_sec": retry_after},
                    status_code=429,
                    headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(limit)},
                )
        except Exception as e:
            logger.warning("rate_limit: Redis op failed, allowing: %s", e)
        return await call_next(request)
