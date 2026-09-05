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
"""

import re

_PAREN_SUFFIX_RE = re.compile(r"\s*\([^()]*\)\s*$")
_DIGIT_RUN_RE = re.compile(r"\d+")


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
    stripped = _PAREN_SUFFIX_RE.sub("", value).strip()
    return stripped or value


def policy_id_key(value: str | None) -> str:
    """Return a match key that ignores cosmetic policy-ID reformatting.

    Normalizes the value and then strips insignificant leading zeros from
    every digit run, so ``"007-916-407357 (8296857)"``,
    ``"007-916-407357 (08296857)"`` and ``"7-916-407357"`` all share a key.
    Use for comparisons only — never persist the key as the policy ID.

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
    if not normalized:
        return ""
    return _DIGIT_RUN_RE.sub(lambda m: m.group(0).lstrip("0") or "0", normalized).casefold()
