"""
FraudShield AI - Structured logging (PART 14, Week 14 Day 5)
================================================================
Logs request method/path/status/latency + key events (login, prediction,
alert creation, admin actions) WITHOUT logging passwords or full JWTs.
"""
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("fraudshield")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.time()
        response = await call_next(request)
        latency_ms = round((time.time() - start) * 1000, 2)
        logger.info(
            "%s %s -> %s (%sms)",
            request.method, request.url.path, response.status_code, latency_ms,
        )
        return response
