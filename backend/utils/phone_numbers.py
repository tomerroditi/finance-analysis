"""Israeli mobile-number normalization for providers that need E.164 input.

OneZero's OTP endpoint only accepts a full international number
(``+9725XXXXXXXX``). Users naturally type the local form (``05X-XXXXXXX``), so
every entry point runs the value through :func:`normalize_israeli_mobile`
before it is stored or sent. Stdlib-only so both the backend and the scraper
can import it (see ``backend/utils/policy_ids.py`` for why shared helpers live
on the backend side).
"""

import re

__all__ = ["ISRAELI_MOBILE_RE", "normalize_israeli_mobile"]

ISRAELI_MOBILE_RE = re.compile(r"^\+9725\d{8}$")

_SEPARATORS_RE = re.compile(r"[\s\-().]")


def normalize_israeli_mobile(phone: str) -> str:
    """Rewrite an Israeli mobile number into ``+9725XXXXXXXX`` form.

    Accepts the local form (``050-1234567``), the bare subscriber form
    (``501234567``) and the international forms (``972501234567``,
    ``+972 50 123 4567``, ``+972-050-1234567``). Anything it cannot
    recognise is returned with separators stripped but otherwise untouched,
    so callers decide whether to reject it via :data:`ISRAELI_MOBILE_RE`.

    Parameters
    ----------
    phone : str
        The phone number as the user typed it.

    Returns
    -------
    str
        The ``+9725XXXXXXXX`` form when the input is a recognisable Israeli
        mobile number, else the separator-stripped input.
    """
    compact = _SEPARATORS_RE.sub("", phone or "")
    digits = compact.lstrip("+")
    if not digits.isdigit():
        return compact
    if digits.startswith("972"):
        digits = digits[3:]
    elif compact.startswith("+"):
        return compact
    digits = digits.removeprefix("0")
    candidate = f"+972{digits}"
    return candidate if ISRAELI_MOBILE_RE.match(candidate) else compact
