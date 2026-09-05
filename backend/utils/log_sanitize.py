"""Scrub untrusted values before they reach a log line (CWE-117).

Values logged by this app include user-chosen account names and provider
response text. Provider text is genuinely external input: a newline in it
forges what reads as a separate, legitimate log entry, and these logs are
exactly what a user pastes into a bug report. Terminal escapes are worse
still — a log tailed in a terminal will act on them.

Parameterised logging (``logger.info("%s", value)``) does not help here: it
prevents format-string injection, not newline injection, because the value
is still written verbatim into the record.

Use :func:`scrub` on every interpolated value that is not a literal or a
number the code itself produced.
"""

import re

#: Characters that begin a new line (or record) in some log consumer:
#: LF, CR, vertical tab, form feed, NEL, line separator, paragraph
#: separator. Replaced with a visible marker rather than dropped, so a
#: scrubbed value is never silently different from the original.
_LINE_BREAKS = re.compile(r"(?:\r\n|[\n\r\v\f\x85  ])")

#: Remaining C0/C1 control characters, minus tab (legitimate log content)
#: and minus the line breaks handled above. Includes ESC, so ANSI colour
#: and cursor-movement sequences cannot reach a terminal that tails the log.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0e-\x1f\x7f-\x84\x86-\x9f]")

#: Cap on a single interpolated value, so one field cannot flood the log.
MAX_VALUE_LENGTH = 512

_TRUNCATION_MARKER = "…[truncated]"


def scrub(value: object) -> str:
    """Render ``value`` as a single-line, control-character-free string.

    Parameters
    ----------
    value : object
        Any value destined for a log line. Coerced with ``str`` first, so a
        hostile ``__str__`` cannot smuggle a newline past the scrub.

    Returns
    -------
    str
        The value with line breaks replaced by a literal ``\\n`` marker,
        other control characters removed, and the result capped at
        :data:`MAX_VALUE_LENGTH` characters.

    Examples
    --------
    >>> scrub("Main Account")
    'Main Account'
    >>> scrub("ok\\nERROR forged")
    'ok\\\\nERROR forged'
    """
    text = str(value)
    # The two most important separators are removed with explicit
    # `str.replace` calls rather than folded into the regex below. They are
    # redundant with it — but this is the shape static analysers recognise
    # as a log-injection barrier, and an unrecognised sanitiser leaves the
    # alert open no matter how correct the code is.
    text = text.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    # A lambda, not a replacement string: `re.sub` processes escapes in a
    # replacement, so the literal "\\n" would expand back into a real
    # newline — the scrubber would reinsert the character it just removed.
    text = _LINE_BREAKS.sub(lambda _: "\\n", text)
    text = _CONTROL_CHARS.sub("", text)
    if len(text) > MAX_VALUE_LENGTH:
        text = text[:MAX_VALUE_LENGTH] + _TRUNCATION_MARKER
    return text
