"""
Analysis service package.

Decomposed from the former single-module ``backend/services/
analysis_service.py``:

- ``cashflow`` — income/expenses/debt over time, by-source, by-category,
  and the shared classification-mask helpers.
- ``net_worth`` — net balance / net worth over time and the Sankey data.
- ``forecast`` — current-month cash-flow forecast + monthly-expense trend.
- ``core`` — the public ``AnalysisService`` class assembling the mixins.

The old module path remains as a compatibility shim re-exporting
``AnalysisService``.
"""

from backend.services.analysis.cashflow import CashflowMixin
from backend.services.analysis.core import AnalysisService
from backend.services.analysis.forecast import ForecastMixin
from backend.services.analysis.net_worth import NetWorthMixin

__all__ = [
    "AnalysisService",
    "CashflowMixin",
    "ForecastMixin",
    "NetWorthMixin",
]
