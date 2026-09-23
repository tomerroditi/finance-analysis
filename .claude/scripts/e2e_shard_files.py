#!/usr/bin/env python3
"""
Print the spec files for one e2e shard, packed by recorded duration.

CI runs the suite as a 4-job matrix. Playwright's own ``--shard=i/N`` splits by
test *count*, which left one job at 2.5 m of tests beside another at 1 m — and
the slowest job is the PR's wall clock. This hands CI the same duration-packed
split ``e2e_parallel_isolated.py`` uses locally, read from the committed
``e2e_shard_timings.json``.

Usage (from ``frontend/``)::

    npx playwright test $(python3 ../.claude/scripts/e2e_shard_files.py 2 4)

Paths are printed relative to ``frontend/``, space-separated, lifecycle specs
first — ``demo.setup.ts`` / ``demo.teardown.ts`` must be in every shard or
their projects match nothing and Demo Mode is never prepared.
"""

import sys

from e2e_parallel_isolated import LIFECYCLE_SPECS, load_timings, pack_shards, spec_files


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    index, total = int(sys.argv[1]), int(sys.argv[2])
    if not 1 <= index <= total:
        print(f"shard index {index} is outside 1..{total}", file=sys.stderr)
        return 2
    shard = pack_shards(spec_files(), load_timings(), total)[index - 1]
    print(" ".join([*LIFECYCLE_SPECS, *shard]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
