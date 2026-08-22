# app/core/request_logging.py
"""
Request-ID + access-log middleware (B15 / Phase 3.6).

One log line per request: method, path, status code, duration -- never the
request/response body or the query string, since either could carry
clinical data depending on the route (see app/core/logging.py's module
docstring for the hard rule this exists to protect). request.url.path is
safe to log as-is: any identifier it contains is a UUID primary key (e.g.
/patients/{id}), never a name or NIC.

Reuses an incoming X-Request-ID if the reverse proxy in front of this
service already set one (Caddy does, in the production compose file --
see docker-compose.prod.yml), so a request can be traced end-to-end across
the proxy and this app from one ID; generates one otherwise (e.g. local
dev with no proxy in front). Echoes it back on the response so a client-side
error report can reference the same ID.
"""
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import get_logger, reset_request_id, set_request_id

logger = get_logger("app.request")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = set_request_id(request_id)
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.monotonic() - start) * 1000, 1)
            logger.exception(
                "request_failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            raise
        finally:
            reset_request_id(token)

        duration_ms = round((time.monotonic() - start) * 1000, 1)
        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
