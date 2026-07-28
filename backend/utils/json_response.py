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
from typing import Any

from fastapi.responses import JSONResponse


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
        Containers are only rebuilt when they actually contain one, so the
        common all-finite payload costs a walk and no allocation.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: sanitize_non_finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_non_finite(v) for v in value]
    return value


class SafeJSONResponse(JSONResponse):
    """``JSONResponse`` that degrades non-finite floats to ``null``.

    Matches Starlette's own separators/encoding so the only behavioural
    difference is that NaN and Infinity serialise instead of raising.
    """

    def render(self, content: Any) -> bytes:
        return json.dumps(
            sanitize_non_finite(content),
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")
