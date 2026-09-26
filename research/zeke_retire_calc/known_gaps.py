#!/usr/bin/env python3
"""Print the `KNOWN_GAPS` a corpus run currently needs.

`test_corpus_parity` bounds every run outside its tolerance by name, with a
reason. This replays the corpus and prints, for each run over the bound, a
bound about a third above its current gap — room for float noise, not for a
regression — grouped by fixture family so a reason can be written once per
cause.

    python research/zeke_retire_calc/known_gaps.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "tests" / "backend" / "unit" / "fire"))

import parity  # noqa: E402
from test_corpus_parity import TOLERANCE, DISPLAY_PRECISION  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    for report in parity.diff_many(parity.corpus(charted=True)):
        bound = max(TOLERANCE, DISPLAY_PRECISION * report.scale)
        if report.error or report.worst < bound:
            continue
        print(f'    "{report.name}": ({report.worst * 1.35:,.0f}, ""),'
              f"  # {report.relative:.4%}")


if __name__ == "__main__":
    main()
