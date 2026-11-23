"""Tiny in-memory sliding-window rate limiter (per client IP). Use gateway/Redis limits for multi-instance prod."""
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, per_minute: int = 600):
        super().__init__(app)
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if self.per_minute <= 0 or request.url.path.endswith("/health"):
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        q = self.hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            return JSONResponse({"detail": "Rate limit exceeded. Try again shortly."}, status_code=429)
        q.append(now)
        return await call_next(request)
