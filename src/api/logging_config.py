"""结构化日志：request_id + 耗时。"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        t0 = time.perf_counter()
        logger = logging.getLogger("filekg.http")
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.exception(
                "request_failed method=%s path=%s request_id=%s elapsed_ms=%.1f",
                request.method,
                request.url.path,
                request_id,
                elapsed_ms,
            )
            raise
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "request method=%s path=%s status=%s request_id=%s elapsed_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            request_id,
            elapsed_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
