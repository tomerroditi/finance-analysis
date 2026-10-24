"""
Insight cards package.

Each card the dashboard strip shows is its own rule, a function of one shared,
per-request ``InsightContext``:

- ``context`` — ``InsightContext``: the memoized inputs every rule reads
  (forecast, spending baseline, planned spend, envelope rows, recurring
  detection, monthly category spend, dismissals).
- ``pace`` — ``overspendPace`` / ``onTrack``.
- ``category_spike`` — ``categorySpike``.
- ``recurring`` — ``recurringToReview`` / ``newRecurring`` / ``priceIncrease``
  / ``priceDecrease``.
- ``large_transaction`` — ``largeTransaction``.
- ``core`` — ``InsightsService``: runs the rules, keeps one event to one card,
  ranks and caps the strip, and records dismissals.
"""

from backend.services.insights.core import InsightsService

__all__ = ["InsightsService"]
