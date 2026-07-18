"""
Compatibility shim — the investments service now lives in
``backend.services.investments``.

Kept so existing ``from backend.services.investments_service import
InvestmentsService`` imports keep working. New code should import from
``backend.services.investments`` (or its submodules ``core``,
``snapshots``, ``valuation``, ``insurance_sync``) directly.

Note: tests that monkeypatch module-level names (``date``, ``datetime``)
must target the defining submodule (e.g.
``backend.services.investments.valuation.date``) — patching this shim's
re-exports does not affect the implementation modules.
"""

from backend.services.investments import (
    InsuranceSyncMixin,
    InvestmentsService,
    SnapshotsMixin,
    ValuationMixin,
)

__all__ = [
    "InsuranceSyncMixin",
    "InvestmentsService",
    "SnapshotsMixin",
    "ValuationMixin",
]
