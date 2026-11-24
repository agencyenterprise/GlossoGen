"""Keeping request credentials out of the web server's access log.

An `EventSource` cannot set an `Authorization` header, so the browser sends its
session token as a `?token=` query parameter, and the identity middleware accepts
any bearer there. uvicorn's access log writes each request's path with its query
string, so without this filter every such token lands in the log in the clear.

The filter covers the HTTP access log only. uvicorn logs a WebSocket handshake's
path and query on `uvicorn.error` instead; the server has no WebSocket routes, and
one that accepted `?token=` would need that logger redacted too.
"""

import logging
import urllib.parse

REDACTED_VALUE = "[redacted]"

_CREDENTIAL_QUERY_PARAMETERS = frozenset({"token"})
_ACCESS_LOGGER_NAME = "uvicorn.access"
_ACCESS_LOG_PATH_ARG_INDEX = 2


class RedactQueryCredentials(logging.Filter):
    """Replace credential query-parameter values in uvicorn access-log records.

    uvicorn logs each request as ``(client_addr, method, path_with_query,
    http_version, status)`` arguments. The filter rewrites the path argument and
    leaves every other part of the record as it was.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact the record's path argument in place; never drop the record."""
        args = record.args
        if not isinstance(args, tuple) or len(args) <= _ACCESS_LOG_PATH_ARG_INDEX:
            return True
        path = args[_ACCESS_LOG_PATH_ARG_INDEX]
        if not isinstance(path, str):
            return True
        redacted = redact_query_credentials(path_with_query=path)
        if redacted == path:
            return True
        record.args = (
            args[:_ACCESS_LOG_PATH_ARG_INDEX] + (redacted,) + args[_ACCESS_LOG_PATH_ARG_INDEX + 1 :]
        )
        return True


def redact_query_credentials(path_with_query: str) -> str:
    """Return the path with each credential parameter's value replaced.

    Parameter names are compared after percent-decoding, as Starlette does when the
    middleware reads them, so ``%74oken=`` is redacted too. Every other parameter
    keeps its original spelling.
    """
    path, separator, query = path_with_query.partition("?")
    if not separator:
        return path_with_query
    pairs: list[str] = []
    for pair in query.split("&"):
        name, equals, _value = pair.partition("=")
        if equals and urllib.parse.unquote_plus(name) in _CREDENTIAL_QUERY_PARAMETERS:
            pairs.append(f"{name}={REDACTED_VALUE}")
        else:
            pairs.append(pair)
    return f"{path}?{'&'.join(pairs)}"


def redact_credentials_in_access_log() -> None:
    """Attach the redaction filter to uvicorn's access logger, once.

    Called when the server app is imported. uvicorn applies its logging config
    before it imports the app, and `logging.config.dictConfig` keeps a logger's
    existing filters, so the filter holds under `glossogen serve`, `make dev` and a
    plain `uvicorn` command alike.
    """
    access_logger = logging.getLogger(_ACCESS_LOGGER_NAME)
    if any(isinstance(existing, RedactQueryCredentials) for existing in access_logger.filters):
        return
    access_logger.addFilter(RedactQueryCredentials())
