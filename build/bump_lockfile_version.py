"""Set the app version in ``frontend/package-lock.json`` during a release bump.

Commitizen's ``version_files`` rewrites every line matching a pattern, and in
the lockfile the root package's ``"version"`` line is indented exactly like
every dependency's — so whenever a dependency shares the app version (at
2.0.0, eight did) the bump would rewrite those too and break ``npm ci``.
This runs as a ``pre_bump_hook`` instead and rewrites only the two fields
that belong to the app: the top-level ``version`` and ``packages[""].version``.
Commitizen commits with ``-a``, so the edit lands in the bump commit.

Usage: ``python build/bump_lockfile_version.py [NEW_VERSION]`` — the version
defaults to ``$CZ_PRE_NEW_VERSION``, which Commitizen sets for the hook.
"""

import json
import os
import re
import sys
from pathlib import Path

LOCKFILE = Path(__file__).resolve().parents[1] / "frontend" / "package-lock.json"

_TOP_LEVEL = re.compile(r'^(  "version": ")[^"]*(",?)$')
_ROOT_ENTRY = re.compile(r'^    "": \{$')
_ROOT_VERSION = re.compile(r'^(      "version": ")[^"]*(",?)$')
_ENTRY_END = re.compile(r"^    \},?$")


def bump(text: str, new_version: str) -> str:
    """Return the lockfile text with the app's two version fields set.

    Parameters
    ----------
    text : str
        The lockfile as npm writes it (two-space indentation).
    new_version : str
        The version to write.

    Returns
    -------
    str
        The same text with only the top-level and ``packages[""]`` version
        lines changed.

    Raises
    ------
    ValueError
        If either field is not where npm puts it, or the result does not
        parse back with both fields set.
    """
    lines = text.split("\n")
    top = next((i for i, line in enumerate(lines) if _TOP_LEVEL.match(line)), None)
    start = next((i for i, line in enumerate(lines) if _ROOT_ENTRY.match(line)), None)
    root = None
    if start is not None:
        for i in range(start + 1, len(lines)):
            if _ENTRY_END.match(lines[i]):
                break
            if _ROOT_VERSION.match(lines[i]):
                root = i
                break
    if top is None or root is None:
        raise ValueError("package-lock.json: app version fields not found")

    lines[top] = _TOP_LEVEL.sub(rf"\g<1>{new_version}\g<2>", lines[top])
    lines[root] = _ROOT_VERSION.sub(rf"\g<1>{new_version}\g<2>", lines[root])
    bumped = "\n".join(lines)

    lock = json.loads(bumped)
    if lock["version"] != new_version or lock["packages"][""]["version"] != new_version:
        raise ValueError("package-lock.json: bump did not land on the app fields")
    return bumped


def main() -> None:
    """Rewrite the lockfile in place with the new version."""
    new_version = sys.argv[1] if len(sys.argv) > 1 else os.environ["CZ_PRE_NEW_VERSION"]
    LOCKFILE.write_text(bump(LOCKFILE.read_text(encoding="utf-8"), new_version), encoding="utf-8")


if __name__ == "__main__":
    main()
