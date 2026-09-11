"""Severance (פיצויים) redemption at retirement.

Redeeming severance takes the *entitling employer* component out of the pension
— so the annuity shrinks — hands the full amount to the checking account, and
bills the tax separately over a spread. All of it is verified in notes/05.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.services.fire import israeli_tax

ANNUAL_EXEMPT_CEILING = 13_300.0
"""Exempt severance per year of service, as the reference has it."""

OFFSET_NUMERATOR = 1.35
OFFSET_DENOMINATOR = 180.0
"""נוסחת הקיזוז: taking severance exempt permanently reduces the monthly
pension exemption by `exempt * 1.35 / 180`. Verified at 2,520.0 and 1,097.2."""

SPREAD_YEARS_PER_SERVICE_YEARS = 4
MAX_SPREAD_YEARS = 6
"""Israeli law allows one tax year of spread per four years of service, capped
at six. Only a single data point confirms this (11 years of service producing a
two-year spread), so it is an inference — see notes/05."""


@dataclass
class SeveranceRedemption:
    """The outcome of redeeming severance in a given month."""

    gross: float
    exempt: float
    taxable: float
    spread_months: int
    monthly_tax: float
    exemption_offset: float
    """Permanent monthly reduction of the pension's own tax exemption."""

    @property
    def monthly_tax_window(self) -> range:
        return range(self.spread_months)


def spread_years(service_years: int) -> int:
    """Tax years the taxable part is spread over."""
    return max(1, min(service_years // SPREAD_YEARS_PER_SERVICE_YEARS, MAX_SPREAD_YEARS))


def redeem(pension_balance: float, mukeret_pct: float, redemption_year: int,
           work_start_year: int | None) -> SeveranceRedemption:
    """Redeem the entitling employer severance component.

    Only `balance × (1 − mukeret) × 0.4` is redeemable — the *recognised*
    severance component stays in the pension and keeps paying an annuity.
    """
    from backend.services.fire.pension import TAGMULIM_SHARE

    gross = pension_balance * (1 - mukeret_pct / 100) * (1 - TAGMULIM_SHARE)
    service_years = max(redemption_year - (work_start_year or redemption_year), 0)
    exempt = min(gross, ANNUAL_EXEMPT_CEILING * service_years)
    taxable = gross - exempt

    years = spread_years(service_years)
    months = years * 12
    monthly_tax = (
        israeli_tax.monthly_income_tax(taxable / months) if taxable > 0 else 0.0
    )
    return SeveranceRedemption(
        gross=gross,
        exempt=exempt,
        taxable=taxable,
        spread_months=months if taxable > 0 else 0,
        monthly_tax=monthly_tax,
        exemption_offset=exempt * OFFSET_NUMERATOR / OFFSET_DENOMINATOR,
    )
