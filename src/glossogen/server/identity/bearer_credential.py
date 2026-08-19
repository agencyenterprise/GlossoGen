"""Extraction of a bearer credential from a request.

Two variants, because two callers need different things. The identity middleware
accepts a credential from either the header or the query string; an endpoint called
by a signed-in browser accepts only the header.
"""

from starlette.requests import Request


def bearer_from_header(request: Request) -> str | None:
    """Return the ``Authorization: Bearer`` credential, or ``None``."""
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[len("Bearer ") :].strip()
    if not token:
        return None
    return token


def bearer_from_header_or_query(request: Request) -> str | None:
    """Return the bearer credential from the header, else the ``token`` query param.

    SSE endpoints are consumed via ``EventSource``, which cannot set an
    ``Authorization`` header, so those requests carry the credential as a ``?token=``
    query parameter instead. The header takes precedence when both are present.
    """
    from_header = bearer_from_header(request=request)
    if from_header is not None:
        return from_header
    query_token = request.query_params.get("token", "").strip()
    if not query_token:
        return None
    return query_token
