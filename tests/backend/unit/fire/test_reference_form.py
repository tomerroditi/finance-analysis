"""Reading the reference's flat form into a plan, where blank and missing differ."""

from __future__ import annotations

from backend.services.fire.reference_form import plan_from_reference


def _fee(**row: str) -> float:
    payload = {"num_portfolio_fields": "1", "portfolioBalance1": "100000", **row}
    return plan_from_reference(payload).portfolios[0].annual_fee_pct


class TestPortfolioFee:
    """The portfolio fee: the reference's 0.1% default applies only when the field is absent."""

    def test_blank_fee_is_no_fee(self):
        """A fee left blank is 0% — a 3% deposit with a blank fee grew 3.000% a year there."""
        assert _fee(portfolioFee1="") == 0.0

    def test_missing_fee_is_the_default(self):
        """A form that never sent the field gets the reference's own 0.1%."""
        assert _fee() == 0.1

    def test_typed_fee_is_kept(self):
        """A fee the user typed is used as is."""
        assert _fee(portfolioFee1="0.25") == 0.25
