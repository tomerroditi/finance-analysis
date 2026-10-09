"""Read the decumulation rate straight off an `experiments/surface` fixture."""
import sys
from parity import load, retire_index


def measured_rate(name: str) -> tuple[float, int] | None:
    """`(annual rate %, first retired month)` from the idle portfolio's growth."""
    fixture = load(name)
    charts = fixture.get("charts") or {}
    if not charts.get("asset_plot"):
        return None
    series = next(d["data"][1:-1] for d in charts["asset_plot"]["datasets"]
                  if "עובר" not in d["label"])
    start = retire_index(fixture) + 1
    end = len(series) - 2
    factor = (series[end] / series[start]) ** (1 / (end - start))
    return 100 * (factor ** 12 - 1), start


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name in sys.argv[1:]:
        print(name, measured_rate(name))
