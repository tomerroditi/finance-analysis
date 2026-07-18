"""
Compatibility shim — the analysis service now lives in
``backend.services.analysis``.

Kept so existing ``from backend.services.analysis_service import
AnalysisService`` imports keep working. New code should import from
``backend.services.analysis`` (or its submodules ``core``, ``cashflow``,
``net_worth``, ``forecast``) directly.

Note: tests that monkeypatch module-level names must target the defining
submodule (e.g. ``backend.services.analysis.forecast``) — patching this
shim's re-exports does not affect the implementation modules.
"""

from backend.services.analysis import (
    AnalysisService,
    CashflowMixin,
    ForecastMixin,
    NetWorthMixin,
)

__all__ = [
    "AnalysisService",
    "CashflowMixin",
    "ForecastMixin",
    "NetWorthMixin",
]
