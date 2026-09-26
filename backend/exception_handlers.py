"""Map exceptions escaping the routes to JSON error responses."""

import logging
import math
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.errors import AppException

logger = logging.getLogger(__name__)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Answer a domain exception with its class's status and message.

    Parameters
    ----------
    request : Request
        Request whose handling raised.
    exc : AppException
        The domain exception.

    Returns
    -------
    JSONResponse
        ``{"detail": exc.message}`` at ``exc.status_code``; a 5xx gets the
        generic unhandled-error body instead, never the message.
    """
    if exc.status_code >= 500:
        return await unhandled_exception_handler(request, exc)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


def _sanitize_non_finite(value: Any) -> Any:
    """Replace non-finite floats with their ``repr``, recursing into containers.

    Parameters
    ----------
    value : Any
        JSON-encodable value.

    Returns
    -------
    Any
        ``value`` with every ``NaN``/``Infinity`` float stringified.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {k: _sanitize_non_finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_non_finite(v) for v in value]
    return value


async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """422 handler that survives non-finite floats in the invalid input.

    Request models reject ``NaN``/``Infinity`` (``allow_inf_nan=False`` on
    ``ApiRequestModel``), but the default handler echoes the offending input
    back in the error body — and ``json.dumps`` cannot serialize a non-finite
    float, turning the 422 into a 500. Stringify those values instead.

    Parameters
    ----------
    request : Request
        Request that failed validation.
    exc : RequestValidationError
        The validation error.

    Returns
    -------
    JSONResponse
        422 with the sanitized error list.
    """
    return JSONResponse(
        status_code=422,
        content={"detail": _sanitize_non_finite(jsonable_encoder(exc.errors()))},
    )


async def overflow_error_handler(request: Request, exc: OverflowError) -> JSONResponse:
    """Map ``OverflowError`` to ``422 Unprocessable Entity``.

    SQLite INTEGER is 64-bit signed (max 2**63 - 1). When a path parameter
    exceeds that, SQLAlchemy raises ``OverflowError`` while binding the
    statement. Treat it as a client input problem rather than a server bug
    so the schemathesis fuzz job stays clean.

    Parameters
    ----------
    request : Request
        Request whose handling raised.
    exc : OverflowError
        The overflow.

    Returns
    -------
    JSONResponse
        422 with a fixed message.
    """
    return JSONResponse(
        status_code=422,
        content={"detail": "Numeric path parameter exceeds supported range"},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Swallow unexpected exceptions with a generic 500 response.

    Messages the service layer intentionally surfaces travel as
    ``AppException`` subclasses and are answered by
    :func:`app_exception_handler`. Anything that reaches this handler is an
    unhandled bug — returning ``str(exc)`` would leak stack frames,
    SQL fragments, file paths, or secrets present in the exception message.
    The real detail is kept in the server log for operators to inspect.

    Parameters
    ----------
    request : Request
        Request whose handling raised.
    exc : Exception
        The unhandled exception.

    Returns
    -------
    JSONResponse
        ``500 {"detail": "Internal server error"}``.
    """
    logger.error(
        "Unhandled exception handling %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Install the API's exception handlers on ``app``.

    Parameters
    ----------
    app : FastAPI
        Application to install the handlers on.
    """
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(
        RequestValidationError, request_validation_exception_handler
    )
    app.add_exception_handler(OverflowError, overflow_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
