"""FastAPI exception handlers that log full tracebacks for every server error.

Starlette renders ``HTTPException`` instances straight to JSON responses
without logging, so a deliberately raised ``HTTPException(status_code=500)``
returns a 500 with no traceback. This handler logs the traceback for every
5xx ``HTTPException`` before deferring to the default response. Genuinely
unhandled exceptions are already logged with a traceback by uvicorn, so they
are left to the default handling.
"""

import logging

from fastapi import FastAPI
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


async def _log_5xx_http_exception(request: Request, exc: Exception) -> Response:
    """Log a traceback for 5xx HTTPExceptions, then defer to the default handler."""
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    if exc.status_code >= 500:
        logger.exception(
            "%d on %s %s: %s",
            exc.status_code,
            request.method,
            request.url.path,
            exc.detail,
        )
    return await http_exception_handler(request=request, exc=exc)


def register_error_logging_handlers(app: FastAPI) -> None:
    """Register the 5xx-HTTPException traceback logger on the app."""
    app.add_exception_handler(
        exc_class_or_status_code=StarletteHTTPException,
        handler=_log_5xx_http_exception,
    )
