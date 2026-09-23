"""Stable identity keys for provider policy IDs.

Providers hand out policy identifiers as display strings, and those strings
are not stable: HaPhoenix reformatted ``"007-916-407357 (8296857)"`` into
``"007-916-407357 (08296857)"`` in September 2026 without any account
actually changing. Every downstream identity — the insurance account row, the
linked Keren Hishtalmut investment, and the scraped transaction dedup key —
is derived from that string, so a cosmetic reformat forks the data.

``normalize_policy_id`` strips the volatile parenthesised internal ID that
providers append, keeping a display-friendly policy number. ``policy_id_key``
goes further and returns a leading-zero-insensitive key for *matching* only —
stored values keep their original digits.

Two providers can also print the *same* policy differently: the pension
clearing house (Mislaka) reports HaPhoenix's ``007-925-053655`` as
``7-925-053655-0``, with a ``-0`` sub-account suffix HaPhoenix never shows.
``policy_id_key`` drops that suffix too, so the Mislaka takes over the policy
HaPhoenix created instead of forking it.

This module is the single definition; ``scraper/utils/policy_ids.py``
re-exports it. It lives on the backend side because it encodes *our*
persistence identity model rather than any provider's wire format, and
because importing in the other direction is not possible: ``scraper`` and
``scraper.utils`` transitively import ``httpx`` and Playwright at package
init, which must not be dragged into the backend (the Vercel build ships
neither). It must stay a plain importable module — loading it from a file
path instead breaks the frozen Windows build, where PyInstaller bundles no
``.py`` sources on disk.
"""

import re

_DIGIT_RUN_RE = re.compile(r"\d+")
_ZERO_SUB_ACCOUNT_SUFFIX = "-0"

__all__ = ["normalize_policy_id", "policy_id_key"]


def normalize_policy_id(raw: str | None) -> str:
    """Return the stable, display-friendly portion of a provider policy ID.

    Drops a trailing parenthesised internal identifier and surrounding
    whitespace. Leading zeros are preserved so the value still matches what
    the provider shows the user.

    Parameters
    ----------
    raw : str or None
        Raw policy ID as scraped, e.g. ``"007-916-407357 (08296857)"``.

    Returns
    -------
    str
        Normalized policy ID, e.g. ``"007-916-407357"``. Empty string for
        ``None``. Falls back to the trimmed input when stripping the suffix
        would leave nothing behind.
    """
    if raw is None:
        return ""
    value = str(raw).strip()
    if not value.endswith(")"):
        return value

    # Deliberately not a regex: the natural pattern here (``\s*\([^()]*\)\s*$``)
    # backtracks quadratically over a long run of spaces, and this runs on
    # provider-supplied text. rfind + a nesting check is linear and matches the
    # same shape — a trailing "(...)" group containing no parentheses of its own.
    opener = value.rfind("(")
    if opener == -1 or ")" in value[opener + 1 : -1]:
        return value
    stripped = value[:opener].strip()
    return stripped or value


def policy_id_key(value: str | None) -> str:
    """Return a match key that ignores cosmetic policy-ID reformatting.

    Normalizes the value, drops a trailing ``-0`` sub-account suffix, and
    strips insignificant leading zeros from every digit run, so
    ``"007-916-407357 (8296857)"``, ``"007-916-407357 (08296857)"``,
    ``"7-916-407357"`` and ``"7-916-407357-0"`` all share a key. Use for
    comparisons only — never persist the key as the policy ID.

    Parameters
    ----------
    value : str or None
        A raw or normalized policy ID.

    Returns
    -------
    str
        Comparison key. Empty string for ``None`` or an empty value.
    """
    normalized = normalize_policy_id(value)
    if normalized.endswith(_ZERO_SUB_ACCOUNT_SUFFIX) and len(normalized) > 2:
        normalized = normalized[: -len(_ZERO_SUB_ACCOUNT_SUFFIX)]
    if not normalized:
        return ""
    return _DIGIT_RUN_RE.sub(
        lambda m: m.group(0).lstrip("0") or "0", normalized
    ).casefold()
