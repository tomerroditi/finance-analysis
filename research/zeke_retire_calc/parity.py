#!/usr/bin/env python3
"""One differ for every recorded run: all three charts, every month.

The reference publishes three monthly charts — assets, income and expenses —
plus net worth. This module replays a fixture through our engine at the
reference's own retirement month and reports, per series, the worst gap and
the first month it opens. The headline number is **relative**: the worst gap on
any series divided by the run's peak net worth, which is what "under 0.1%"
means for a plan.

    python research/zeke_retire_calc/parity.py                 # whole corpus
    python research/zeke_retire_calc/parity.py fx_ gb_         # by prefix
    python research/zeke_retire_calc/parity.py fx_m67_20m -v   # one run, every series
    python research/zeke_retire_calc/parity.py --worst 20      # the 20 worst

Replays fan out over processes; the corpus takes a few seconds.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from backend.services.fire.engine import Simulator  # noqa: E402
from backend.services.fire.models import PortfolioDesignation, PortfolioType  # noqa: E402
from backend.services.fire.reference_form import plan_from_reference  # noqa: E402

FIXTURES = HERE / "fixtures"
RECORDED_IN = date(2026, 9, 1)
"""Calendar month the fixtures were recorded in — the simulation's month zero.

A fixture recorded later carries its own month in `meta.recorded_in`."""

TYPE_LABELS = {
    PortfolioType.BROKER_IL: "תיק בברוקר בארץ",
    PortfolioType.IBKR: 'תיק בברוקר בחו"ל',
    PortfolioType.GEMEL: "קופת גמל להשקעה",
    PortfolioType.POLISA: "פוליסת חיסכון",
    PortfolioType.KASPIT: "קרן כספית",
    PortfolioType.PIKADON: "פיקדון",
}
"""What the reference calls a portfolio the user did not name."""


def _path(name: str) -> Path:
    return FIXTURES / f"{name}.json.gz"


def exists(name: str) -> bool:
    """Whether a fixture of this name is recorded."""
    return _path(name).exists() or (FIXTURES / f"{name}.json").exists()


def load(name: str) -> dict:
    """A recorded fixture by name.

    Stored gzipped and compact: a run's charts are ~50k of numbers, and the
    corpus grows by hundreds of runs per experiment. A plain `.json` of the
    same name is still read, for a fixture written by hand.
    """
    path = _path(name)
    if path.exists():
        return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def save(name: str, fixture: dict) -> None:
    """Record a fixture under `name`."""
    FIXTURES.mkdir(exist_ok=True)
    body = json.dumps(fixture, ensure_ascii=False, separators=(",", ":"))
    # mtime=0 keeps the bytes a pure function of the content, so an unchanged
    # fixture never shows up as modified.
    _path(name).write_bytes(gzip.compress(body.encode("utf-8"), 9, mtime=0))
    (FIXTURES / f"{name}.json").unlink(missing_ok=True)


def recorded_in(fixture: dict) -> date:
    """The month the reference treated as "now" for this fixture."""
    stamp = fixture.get("meta", {}).get("recorded_in")
    return date.fromisoformat(stamp) if stamp else RECORDED_IN


def retire_index(fixture: dict) -> int:
    """First fully retired month, read from the reference's own output.

    The printed date is the last *working* month (notes/08). A plan that never
    reaches its goals prints no date, so fall back to the month pay stops.
    """
    today = recorded_in(fixture)
    match = re.search(r"ב-(\d{2})/(\d{4})", fixture.get("summary", ""))
    if match:
        month, year = int(match.group(1)), int(match.group(2))
        return (year - today.year) * 12 + (month - today.month) + 1
    try:
        work = next(d["data"][1:-1] for d in fixture["charts"]["income_plot"]["datasets"]
                    if d["label"] == "עבודה")
    except (KeyError, StopIteration):
        return 10 ** 9
    return next((i for i in range(1, len(work)) if work[i] == 0 and work[i - 1] > 0),
                10 ** 9)


# -- chart label -> engine key ------------------------------------------------

def _portfolio_index(plan, text: str) -> int | None:
    for match in (lambda p: p.description and p.description == text.strip(),
                  lambda p: p.description and p.description in text,
                  lambda p: TYPE_LABELS.get(p.kind, "\0") in text):
        hits = [i for i, p in enumerate(plan.portfolios) if match(p)]
        if len(hits) == 1:
            return hits[0]
    return 0 if len(plan.portfolios) == 1 else None


def _whose(plan, label: str) -> str:
    if plan.partner is not None and plan.partner.name:
        if label.rstrip().endswith(plan.partner.name):
            return "_partner"
    return ""


def _gemel_keys(plan, suffix: str) -> list[str]:
    wanted = (PortfolioDesignation.MUKERET_PARTNER if suffix
              else PortfolioDesignation.MUKERET_MAIN)
    return [f"gemel{i}" for i, p in enumerate(plan.portfolios)
            if p.kind is PortfolioType.GEMEL and p.designation is wanted]


def income_keys(label: str, plan) -> list[str] | None:
    """Engine `incomes` keys a row of `income_plot` is the sum of."""
    if label.startswith("עבודה"):
        return ["work"]
    if label.startswith("הכנסות חד פעמיות"):
        return ["one_time"]
    if label.startswith("משיכה מעובר ושב"):
        return ["cash"]
    if label.startswith("משיכה מתיק"):
        index = _portfolio_index(plan, label[len("משיכה מתיק"):])
        return None if index is None else [f"portfolio{index}"]
    if label.startswith("משיכה מקרן השתלמות"):
        return [f"keren{i}" for i in range(len(plan.kranot_hishtalmut))]
    if label.startswith("קיצבת זיקנה"):
        return ["state_pension" + _whose(plan, label)]
    if label.startswith("מוכרת גמל להשקעה"):
        return _gemel_keys(plan, _whose(plan, label))
    if label.startswith("מוכרת"):
        return ["recognised" + _whose(plan, label)]
    if label.startswith("מזכה"):
        return ["entitling" + _whose(plan, label)]
    if label.startswith("החתיכה החסרה"):
        return ["shortfall"]
    return None


def expense_keys(label: str, plan) -> list[str] | None:
    """Engine `expenses` keys a row of `expense_plot` is the sum of."""
    if label.startswith("הוצאות שוטפות"):
        return ["living"]
    if label.startswith("יעדים"):
        return ["one_time"]
    if label.startswith("הוצאה לא מתוכננת"):
        return ["unplanned"]
    if label.startswith("הפרשה לעובר ושב"):
        return ["buffer"]
    if label.startswith("הלוואות"):
        return ["loans"]
    if label.startswith("הפקדה ל"):
        index = _portfolio_index(plan, label[len("הפקדה ל"):])
        return None if index is None else [f"deposit_portfolio{index}"]
    if label.startswith("מס על רווחי"):
        index = _portfolio_index(plan, label[len("מס על רווחי"):])
        return None if index is None else [f"capital_gains_tax{index}"]
    if label.startswith("מס הכנסה"):
        return ["income_tax" + _whose(plan, label)]
    if label.startswith("ביטוח לאומי"):
        return ["national_insurance" + _whose(plan, label)]
    return None


def asset_keys(label: str, plan) -> list[str] | None:
    """Engine `assets` keys a row of `asset_plot` is."""
    if "עובר" in label:
        return ["cash"]
    if "פנסיה" in label:
        return [f"pension{1 if plan.partner and _whose(plan, label) else 0}"]
    if "השתלמות" in label:
        return [f"keren{i}" for i in range(len(plan.kranot_hishtalmut))]
    if "נדל" in label or "דירה" in label:
        return [f"realestate{i}" for i in range(len(plan.real_estate))]
    index = _portfolio_index(plan, label)
    return None if index is None else [f"portfolio{index}"]


# -- the diff -----------------------------------------------------------------

@dataclass
class Series:
    chart: str
    label: str
    worst: float
    worst_month: int
    first_month: int | None
    """First month the gap exceeds half a shekel, if ever."""
    reference: float
    ours: float


@dataclass
class Report:
    name: str
    retire_index: int
    scale: float
    """Peak |net worth| in the reference — the denominator of `relative`."""
    series: list[Series] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)
    error: str | None = None
    result: object = field(default=None, repr=False)
    """Our `SimulationResult`, for callers that check more than the charts."""
    months: tuple[int, int] = (0, 0)
    """`(ours, reference)` horizon lengths — they must agree."""

    @property
    def worst(self) -> float:
        return max((s.worst for s in self.series), default=0.0)

    @property
    def relative(self) -> float:
        return self.worst / self.scale if self.scale else 0.0

    @property
    def first_month(self) -> int | None:
        months = [s.first_month for s in self.series if s.first_month is not None]
        return min(months) if months else None


def worst_asset_gap(fixture: dict, plan, result) -> float:
    """Largest gap between our asset series and the reference's, any month."""
    worst = 0.0
    for dataset in fixture["charts"]["asset_plot"]["datasets"]:
        keys = asset_keys(dataset["label"], plan)
        if keys is None:
            continue
        reference = dataset["data"][1:-1]
        for month in range(min(len(reference), len(result.months))):
            ours = sum(result.months[month].assets.get(k, 0.0) for k in keys)
            worst = max(worst, abs(ours - reference[month]))
    return worst


def _values(record, attribute: str, keys: list[str]) -> float:
    bucket = getattr(record, attribute) if attribute != "net" else None
    if attribute == "net":
        return record.net_worth
    return sum(bucket.get(k, 0.0) for k in keys)


def diff(name: str, plan_hook=None) -> Report:
    """Replay `name` and compare every charted series, every month."""
    fixture = load(name)
    charts = fixture.get("charts") or {}
    if not charts.get("asset_plot"):
        return Report(name, 0, 0.0, error="no charts (the reference refused the run)")
    plan = plan_from_reference(fixture["overrides"])
    if plan_hook:
        plan_hook(plan)
    index = retire_index(fixture)
    result = Simulator(plan).run(retire_index=index, today=recorded_in(fixture))

    net = (charts.get("netval_plot") or {}).get("datasets") or []
    net_reference = net[0]["data"][1:-1] if net else []
    scale = max((abs(v) for v in net_reference if isinstance(v, (int, float))), default=0.0)
    reference_months = len(charts["asset_plot"]["labels"]) - 2
    report = Report(name, index, scale, result=result,
                    months=(len(result.months), reference_months))

    rows = []
    for chart, mapper, attribute in (("asset_plot", asset_keys, "assets"),
                                     ("income_plot", income_keys, "incomes"),
                                     ("expense_plot", expense_keys, "expenses")):
        for dataset in (charts.get(chart) or {}).get("datasets", []):
            keys = mapper(dataset["label"], plan)
            if keys is None:
                report.unmapped.append(f"{chart}:{dataset['label']}")
                continue
            rows.append((chart, dataset["label"], attribute, keys, dataset["data"][1:-1]))
    if net_reference:
        rows.append(("netval_plot", "net worth", "net", [], net_reference))

    for chart, label, attribute, keys, reference in rows:
        worst, worst_month, first = 0.0, 0, None
        for month in range(min(len(reference), len(result.months))):
            ours = _values(result.months[month], attribute, keys)
            gap = abs(ours - reference[month])
            if gap > worst:
                worst, worst_month = gap, month
            if first is None and gap > 0.5:
                first = month
        ours_at = (_values(result.months[worst_month], attribute, keys)
                   if result.months else 0.0)
        report.series.append(Series(chart, label, worst, worst_month, first,
                                    reference[worst_month] if reference else 0.0, ours_at))
    return report


def printed_retire_index(fixture: dict) -> int | None:
    """The retirement the reference *chose*, or None if it printed none."""
    today = recorded_in(fixture)
    match = re.search(r"ב-(\d{2})/(\d{4})", fixture.get("summary", ""))
    if not match:
        return None
    month, year = int(match.group(1)), int(match.group(2))
    return (year - today.year) * 12 + (month - today.month) + 1


def solver_check(name: str) -> tuple[int | None, int | None]:
    """`(ours, reference)` first retired month, from each side's own solver."""
    from backend.services.fire.solver import solve

    fixture = load(name)
    outcome = solve(plan_from_reference(fixture["overrides"]), recorded_in(fixture))
    # The reference prints a retirement date only for a plan that meets its goals.
    return (outcome.retire_index if outcome.succeeded else None,
            printed_retire_index(fixture))


def _safe_diff(name: str) -> Report:
    try:
        report = diff(name)
        report.result = None  # keep the cross-process payload small
        return report
    except Exception as exc:  # noqa: BLE001 — a crash is a finding, keep going
        return Report(name, 0, 0.0, error=f"{type(exc).__name__}: {exc}")


def corpus(prefixes: list[str] | None = None, charted: bool = False) -> list[str]:
    """Fixture names, optionally only those starting with one of `prefixes`.

    `charted` keeps only runs the reference actually answered — a refused run
    (an input it rejects, a mode that crashes on its side) has nothing to diff.
    """
    names = sorted({p.name.split(".json")[0] for p in FIXTURES.iterdir()
                    if p.name.endswith((".json", ".json.gz"))})
    if prefixes:
        names = [n for n in names if any(n.startswith(p) for p in prefixes)]
    if charted:
        names = [n for n in names if (load(n).get("charts") or {}).get("asset_plot")]
    return names


def diff_many(names: list[str], workers: int | None = None) -> list[Report]:
    """`diff` over many fixtures, in parallel."""
    if len(names) <= 2:
        return [_safe_diff(n) for n in names]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_safe_diff, names, chunksize=4))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prefixes", nargs="*")
    parser.add_argument("-v", "--verbose", action="store_true", help="every series")
    parser.add_argument("--worst", type=int, default=0, help="only the N worst runs")
    parser.add_argument("--threshold", type=float, default=0.001,
                        help="relative error counted as a pass (default 0.1%%)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    reports = diff_many(corpus(args.prefixes))
    ranked = sorted(reports, key=lambda r: (r.error is None, -r.relative))
    if args.worst:
        ranked = ranked[:args.worst]
    for report in ranked:
        if report.error:
            print(f"{report.name:28s} {report.error}")
            continue
        print(f"{report.name:28s} rel {report.relative:9.4%}  worst {report.worst:12,.2f}"
              f"  first>0.5 @m{report.first_month}  retire m{report.retire_index}"
              + (f"  UNMAPPED {report.unmapped}" if report.unmapped else ""))
        if args.verbose:
            for s in sorted(report.series, key=lambda s: -s.worst):
                print(f"    {s.chart:12s} {s.label[:34]:34s} {s.worst:12,.2f} @m{s.worst_month:<4d}"
                      f" ref {s.reference:14,.2f} ours {s.ours:14,.2f}  first@{s.first_month}")
    ok = [r for r in reports if not r.error]
    passing = sum(r.relative < args.threshold for r in ok)
    exact = sum(r.worst < 0.5 for r in ok)
    print(f"\n{len(ok)} runs: {passing} under {args.threshold:.2%} relative, "
          f"{exact} within half a shekel everywhere; "
          f"{len(reports) - len(ok)} without charts")


if __name__ == "__main__":
    main()
