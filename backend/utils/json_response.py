"""JSON response class that renders non-finite floats as ``null``.

Most of this app's payloads originate as pandas DataFrames and reach the
routes via ``to_dict(orient="records")``. pandas represents a SQL ``NULL``
in a numeric or object column as ``NaN``, and pandas 3 does so in cases
where pandas 2 preserved ``None`` — so a nullable column that was fine
before now arrives at serialisation as a float ``NaN``.

Starlette's ``JSONResponse`` dumps with ``allow_nan=False``, so a single
``NaN`` raises ``ValueError`` and the request 500s. That is how a refund
saved without a note took down the whole refunds list.

Serialising with ``allow_nan=True`` instead is *not* a fix: it emits the
bare tokens ``NaN`` / ``Infinity``, which are not valid JSON and make the
browser's ``JSON.parse`` throw. The only correct output is ``null``.

Individual services can (and some do) normalise with
``df.replace({np.nan: None})``, but there are ~26 ``to_dict`` sites and
nothing stops the next one from forgetting. This class is the backstop:
wired in as the app-wide ``default_response_class``, it makes the failure
mode impossible rather than merely fixed in the places we remembered.
"""

import json
import math
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import pandas as pd
from fastapi.responses import JSONResponse, Response


def sanitize_non_finite(value: Any) -> Any:
    """Recursively replace NaN/Infinity floats with ``None``.

    Parameters
    ----------
    value : Any
        Any JSON-encodable structure — dicts, lists, tuples and scalars are
        walked; everything else is returned untouched.

    Returns
    -------
    Any
        The same structure with every non-finite float replaced by ``None``.
        Tuples come back as lists (JSON has only arrays).
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: sanitize_non_finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_non_finite(v) for v in value]
    return value


def _dumps(content: Any, default: Callable[[Any], Any] | None = None) -> bytes:
    """Encode ``content`` as compact UTF-8 JSON, non-finite floats as ``null``.

    The C encoder runs first with ``allow_nan=False``. It raises on the first
    NaN or Infinity, and only then is the payload walked and rebuilt
    (:func:`sanitize_non_finite`) — a walk that cost more than the encoding
    itself on every list endpoint, to fix values that are almost never there.

    Parameters
    ----------
    content : Any
        The JSON-encodable payload.
    default : callable, optional
        ``json.dumps``'s hook for values it cannot encode natively.

    Returns
    -------
    bytes
        The encoded body.
    """
    options: dict[str, Any] = {
        "ensure_ascii": False,
        "allow_nan": False,
        "indent": None,
        "separators": (",", ":"),
        "default": default,
    }
    try:
        return json.dumps(content, **options).encode("utf-8")
    except ValueError:
        return json.dumps(sanitize_non_finite(content), **options).encode("utf-8")


def _encode_temporal(value: Any) -> str:
    """Encode a date or datetime as ISO 8601, as FastAPI's own encoder does.

    Raises
    ------
    TypeError
        For anything else, as ``json.dumps`` expects of a ``default`` hook.
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def records_response(df: pd.DataFrame) -> Response:
    """Serialise a frame as a JSON array of row objects.

    For the big list endpoints. Missing values become ``null`` once, at the
    frame level, rather than through a per-value Python walk, and the route
    returns this response directly so no response-model validation runs over
    every row. The body is what ``df.to_dict(orient="records")`` through
    :class:`SafeJSONResponse` produced: same keys, ``null`` for NaN/NaT,
    numbers through the same encoder, dates and datetimes as ISO strings.

    Parameters
    ----------
    df : pd.DataFrame
        The rows to serve.

    Returns
    -------
    Response
        An ``application/json`` response.
    """
    records = df.astype(object).where(df.notna(), None).to_dict(orient="records")
    return Response(
        content=_dumps(records, default=_encode_temporal),
        media_type="application/json",
    )


class SafeJSONResponse(JSONResponse):
    """``JSONResponse`` that degrades non-finite floats to ``null``.

    Matches Starlette's own separators/encoding so the only behavioural
    difference is that NaN and Infinity serialise instead of raising.
    """

    def render(self, content: Any) -> bytes:
        """Serialise ``content`` to UTF-8 JSON with non-finite floats as ``null``."""
        return _dumps(content)
