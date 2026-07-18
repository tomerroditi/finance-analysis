"""
Investments service package.

Decomposed from the former single-module ``backend/services/
investments_service.py``:

- ``snapshots`` — balance-snapshot CRUD + fixed-rate snapshot generation.
- ``valuation`` — balance resolution, balance-over-time, profit/loss,
  portfolio aggregations, and shared transaction-fetch helpers.
- ``insurance_sync`` — Keren Hishtalmut sync from insurance accounts.
- ``core`` — the public ``InvestmentsService`` class (lifecycle +
  prior-wealth recalc) assembling the mixins.

The old module path remains as a compatibility shim re-exporting
``InvestmentsService``.
"""

from backend.services.investments.core import InvestmentsService
from backend.services.investments.insurance_sync import InsuranceSyncMixin
from backend.services.investments.snapshots import SnapshotsMixin
from backend.services.investments.valuation import ValuationMixin

__all__ = [
    "InsuranceSyncMixin",
    "InvestmentsService",
    "SnapshotsMixin",
    "ValuationMixin",
]
