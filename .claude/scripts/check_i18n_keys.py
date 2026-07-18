#!/usr/bin/env python3
"""CI check: every literal t("...") key must exist in en.json and he.json.

Missing keys silently render the raw key path to users (this exact bug
shipped three times). Dynamic keys (template literals, variables) are out
of scope — only string-literal calls are checked.
"""

import json
import re
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def flatten(d: dict, prefix: str = ""):
    for key, value in d.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from flatten(value, path)
        else:
            yield path


def main() -> int:
    locales = {}
    for name in ("en", "he"):
        with open(FRONTEND / "src" / "locales" / f"{name}.json") as f:
            locales[name] = set(flatten(json.load(f)))

    missing = []
    for path in sorted(FRONTEND.glob("src/**/*.ts*")):
        rel = path.relative_to(FRONTEND)
        if ".test." in path.name or "mocks" in path.parts:
            continue
        src = path.read_text()
        for m in re.finditer(r'[^a-zA-Z_.]t\(\s*"([a-zA-Z0-9_.]+)"', src):
            key = m.group(1)
            if "." not in key:
                continue
            for locale, keys in locales.items():
                if key not in keys:
                    line = src[: m.start()].count("\n") + 1
                    missing.append(f"{rel}:{line}: t(\"{key}\") missing from {locale}.json")

    if missing:
        print("Missing i18n keys:")
        print("\n".join(missing))
        return 1
    print("i18n keys OK: every literal t() key exists in en.json and he.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
