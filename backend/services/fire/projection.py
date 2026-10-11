"""Solve a form, and the optimiser's advice on it, once per form and month.

Solving searches a couple of hundred retirement months, and the advice
searches again on a changed plan; each takes about a second. The dashboard
card, the plan page and the page's Calculate button all ask for the same few
forms, so answers are memoised by the exact form, the decumulation override
and the month they were solved in. A change to the plan or to the tracked data
it follows changes the form, so a stale answer is never served; a new month
changes the key.

The advice is computed only when asked for. The card does not show it, so
the card's request solves without it, and the page's later request for the
same form only adds the advice.
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date

from backend.services.fire.advice import Recommendation, advise
from backend.services.fire.models import Plan
from backend.services.fire.reference_form import plan_from_reference
from backend.services.fire.solver import SolveResult, solve

CACHE_SIZE = 16


@dataclass
class Projection:
    """A solved form: the solver's answer, and the advice once asked for."""

    plan: Plan
    result: SolveResult
    advised: bool = False
    recommendation: Recommendation | None = None


_cache: OrderedDict[tuple, Projection] = OrderedDict()
_lock = threading.Lock()


def project(
    fields: dict[str, str],
    decumulation_return_pct: float | None = None,
    with_advice: bool = True,
    today: date | None = None,
) -> Projection:
    """Solve `fields` from `today`'s month, with the advice if asked for.

    The returned objects are shared with later callers: read them, never
    change them.
    """
    today = (today or date.today()).replace(day=1)
    key = (json.dumps(fields, sort_keys=True), decumulation_return_pct, today)
    with _lock:
        projection = _cache.get(key)
        if projection is not None:
            _cache.move_to_end(key)
    if projection is None:
        plan = plan_from_reference(fields)
        if decumulation_return_pct is not None:
            plan.decumulation_return_pct = decumulation_return_pct
        projection = Projection(plan=plan, result=solve(plan, today))
    if with_advice and not projection.advised:
        projection.recommendation = (
            advise(projection.plan, projection.result, today)
            if projection.result.simulation is not None
            else None
        )
        projection.advised = True
    with _lock:
        _cache[key] = projection
        _cache.move_to_end(key)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return projection


def clear_cache() -> None:
    """Forget every memoised answer."""
    with _lock:
        _cache.clear()
