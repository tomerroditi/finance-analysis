"""
Text formatting utilities for consistent string handling.

This module provides utilities for standardizing text formats,
particularly for category and tag names.
"""

import re
from typing import Optional

# Common initialisms that should remain in all capitals
# These are preserved when converting to title case
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


def to_title_case(text: Optional[str]) -> Optional[str]:
    """
    Convert a string to title case while preserving initialisms.

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
    >>> to_title_case(None)
    None
    """
    if text is None:
        return None

    if not text or not text.strip():
        return text

    def process_word(word: str) -> str:
        """Process a single word, handling hyphens."""
        if not word:
            return word

        # Check if the entire word is an initialism
        if word.upper() in INITIALISMS:
            return word.upper()

        # Handle hyphenated words (e.g., "chat-gpt" -> "Chat-GPT")
        if "-" in word:
            parts = word.split("-")
            processed_parts = []
            for part in parts:
                if part.upper() in INITIALISMS:
                    processed_parts.append(part.upper())
                else:
                    processed_parts.append(part.capitalize())
            return "-".join(processed_parts)

        # Standard word capitalization
        return word.capitalize()

    # Split by whitespace while preserving multiple spaces
    words = re.split(r"(\s+)", text)
    result = []

    for word in words:
        if word.isspace():
            result.append(word)
        else:
            result.append(process_word(word))

    return "".join(result)
