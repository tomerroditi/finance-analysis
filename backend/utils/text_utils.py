"""Text formatting utilities for category and tag names."""

import re

# Initialisms kept in all capitals by ``to_title_case``.
INITIALISMS = frozenset(
    {
        "ATM",
        "BTB",
        "DJ",
        "GPT",
        "USA",
        "P2P",
        "TV",
        "PC",
        "ID",
    }
)


def to_title_case(text: str | None) -> str | None:
    """Convert a string to title case while preserving initialisms.

    Title case means the first letter of each word is capitalized.
    Common initialisms (like ATM, DJ, GPT) are kept in all capitals.

    Parameters
    ----------
    text : str or None
        The string to convert.

    Returns
    -------
    str or None
        The title-cased string, or None if input was None.

    Examples
    --------
    >>> to_title_case("hello world")
    'Hello World'
    >>> to_title_case("atm withdrawal")
    'ATM Withdrawal'
    >>> to_title_case("chat-gpt subscription")
    'Chat-GPT Subscription'
    >>> to_title_case(None) is None
    True
    """
    if text is None:
        return None

    if not text or not text.strip():
        return text

    def process_part(part: str) -> str:
        """Upper-case an initialism, capitalize anything else."""
        return part.upper() if part.upper() in INITIALISMS else part.capitalize()

    def process_word(word: str) -> str:
        """Title-case one word, treating each hyphen-separated part separately."""
        if word.upper() in INITIALISMS:
            return word.upper()
        return "-".join(process_part(part) for part in word.split("-"))

    # The capturing split keeps whitespace runs so spacing survives verbatim.
    words = re.split(r"(\s+)", text)
    return "".join(word if word.isspace() else process_word(word) for word in words)
