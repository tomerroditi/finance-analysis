#!/usr/bin/env python3
"""Run a family of probes against the reference and judge each as it lands.

An experiment is a module in `experiments/` exposing `SCENARIOS`, a dict of
fixture name -> form payload (build them with `scenario.form`). For each one
this records the reference's answer as an ordinary fixture — so every parity
suite picks it up — and immediately replays it:

* **rel / worst** — our gap with nothing supplied, relative to the run's peak
  net worth and in shekels;
* **fit** — the decumulation rate that run actually implies, and the gap left
  once it is supplied (`--fit`). A small second gap beside a large first one
  means the model is right and only the rate it read is wrong.

    python research/zeke_retire_calc/lab.py bridge_weights            # record + judge
    python research/zeke_retire_calc/lab.py bridge_weights --dry      # judge what is on disk
    python research/zeke_retire_calc/lab.py bridge_weights --fit      # also solve each rate

Already-recorded fixtures are skipped unless `--force`, so an interrupted sweep
resumes. The reference is a shared job queue: probes run one at a time with a
pause between them. Design the family so it answers one question.
"""
from __future__ import annotations

import argparse
import importlib
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

import extract  # noqa: E402
import parity  # noqa: E402
import zeke  # noqa: E402


def record(session: zeke.Session, name: str, payload: dict, family: str) -> dict:
    """Submit one scenario and record the answer as fixture `name`."""
    started = time.time()
    answer = session.calc(payload, verbose=False)
    body = answer.get("results", "")
    fixture = {
        "name": name,
        "overrides": payload,
        "calc_success": answer.get("calc_success"),
        "summary": zeke.text(body),
        "charts": extract.charts(body),
        "meta": {"seconds": round(time.time() - started, 1), "job": answer.get("_job"),
                 "family": family, "recorded_in": date.today().replace(day=1).isoformat(),
                 "messages": zeke.text(answer.get("messages_html") or "")},
    }
    parity.save(name, fixture)
    return fixture


def fit_rate(name: str) -> tuple[float, float]:
    """`(rate, worst gap)` — the decumulation return this run implies.

    Golden-section on the worst gap over every series. Only meaningful when the
    run's portfolio actually decumulates.
    """
    def gap(rate: float) -> float:
        def pin(plan) -> None:
            plan.decumulation_return_pct = rate
        return parity.diff(name, plan_hook=pin).worst

    low, high = -1.0, 5.0
    for _ in range(40):
        a, b = low + (high - low) * 0.382, low + (high - low) * 0.618
        if gap(a) < gap(b):
            high = b
        else:
            low = a
    rate = (low + high) / 2
    return rate, gap(rate)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment", help="module name under experiments/")
    parser.add_argument("prefix", nargs="?", default="")
    parser.add_argument("--dry", action="store_true", help="no network; judge what is on disk")
    parser.add_argument("--force", action="store_true", help="re-record what is on disk")
    parser.add_argument("--fit", action="store_true", help="also solve each run's own rate")
    parser.add_argument("--sleep", type=float, default=1.5, help="seconds between probes")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    module = importlib.import_module(f"experiments.{args.experiment}")
    wanted = {n: p for n, p in module.SCENARIOS.items() if n.startswith(args.prefix)}
    print(f"{args.experiment}: {len(wanted)} scenario(s)")
    predict = getattr(module, "predict", None)

    session = None
    for name, payload in wanted.items():
        state = "disk"
        if not args.dry and (args.force or not parity.exists(name)):
            if session is None:
                session = zeke.Session().load()
            time.sleep(args.sleep)
            try:
                fixture = record(session, name, payload, args.experiment)
            except Exception as exc:  # noqa: BLE001 — keep the sweep going
                print(f"{name:26s} FAILED {type(exc).__name__}: {exc}")
                continue
            state = "new " if fixture.get("calc_success") else "REFUSED"
        if not parity.exists(name):
            print(f"{name:26s} not recorded")
            continue
        report = parity.diff(name)
        if report.error:
            print(f"{name:26s} {state} {report.error}")
            continue
        line = (f"{name:26s} {state} rel {report.relative:8.4%} worst {report.worst:11,.2f}"
                f" first@{report.first_month}")
        ours, theirs = parity.solver_check(name)
        line += "  solver ok" if ours == theirs else f"  SOLVER ours m{ours} ref m{theirs}"
        if predict:
            line += f"  predicted {predict(name):.5f}"
        if args.fit:
            rate, left = fit_rate(name)
            line += f"  fit {rate:.5f} -> {left:,.2f}"
        print(line, flush=True)


if __name__ == "__main__":
    main()
