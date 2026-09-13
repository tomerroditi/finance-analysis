"""Unit tests for the two closed-form pieces of the FIRE engine.

Both are pinned to numbers the reference calculator itself produced, quoted in
``research/zeke_retire_calc/notes/``.
"""

from __future__ import annotations

import pytest

from backend.services.fire.loans import balance_at, payment_at, spitzer_payment
from backend.services.fire.models import Loan, LoanType, LotMethod, Portfolio
from backend.services.fire.taxation import TaxableAccount


class TestLoanAmortization:
    """Loan maths, against the reference's own reported payments."""

    def test_spitzer_level_payment(self):
        """A 300k / 5% / 20y equal-instalment loan pays 1,979.9 a month."""
        loan = Loan(initial_sum=300_000, annual_interest_pct=5, term_years=20,
                    kind=LoanType.SPITZER)
        assert spitzer_payment(loan) == pytest.approx(1979.8672, abs=0.001)

    def test_no_payment_in_the_start_month(self):
        """Payments run from one month after the start, never in it."""
        loan = Loan(initial_sum=300_000, annual_interest_pct=5, term_years=20,
                    kind=LoanType.SPITZER)
        assert payment_at(loan, 0) == 0.0
        assert payment_at(loan, 1) == pytest.approx(1979.8672, abs=0.001)
        assert payment_at(loan, 241) == 0.0

    def test_balloon_accrues_and_pays_once(self):
        """A 200k / 5% / 15y balloon repays 422,740.8 in a single bullet."""
        loan = Loan(initial_sum=200_000, annual_interest_pct=5, term_years=15,
                    kind=LoanType.BALOON)
        assert payment_at(loan, 100) == 0.0
        assert payment_at(loan, 180) == pytest.approx(422_740.79, abs=0.05)

    def test_grace_pays_interest_then_principal(self):
        """A 100k / 5% grace loan pays 416.7 monthly, then 100,416.7 at the end."""
        loan = Loan(initial_sum=100_000, annual_interest_pct=5, term_years=10,
                    kind=LoanType.GRACE)
        assert payment_at(loan, 1) == pytest.approx(416.6667, abs=0.001)
        assert payment_at(loan, 120) == pytest.approx(100_416.6667, abs=0.001)
        assert balance_at(loan, 60) == pytest.approx(100_000)

    def test_loan_disappears_once_repaid(self):
        """Nothing is owed after the final payment."""
        loan = Loan(initial_sum=300_000, annual_interest_pct=5, term_years=20,
                    kind=LoanType.SPITZER)
        assert balance_at(loan, 240) == 0.0


class TestCapitalGainsTax:
    """Proportional ("flat") lot accounting at 25%."""

    def test_untaxed_when_there_is_no_gain(self):
        """A portfolio bought at today's price pays no tax on a sale."""
        account = TaxableAccount(balance=100_000, basis=100_000)
        net, tax = account.withdraw_net(5_000)
        assert tax == 0.0
        assert net == pytest.approx(5_000)
        assert account.balance == pytest.approx(95_000)

    def test_grosses_up_for_embedded_gain(self):
        """Netting 5,000 out of a half-gain portfolio costs 5,714.29 gross."""
        account = TaxableAccount(balance=100_000, basis=50_000)
        net, tax = account.withdraw_net(5_000)
        assert net == pytest.approx(5_000)
        assert tax == pytest.approx(714.2857, abs=0.001)
        assert account.balance == pytest.approx(100_000 - 5_714.2857, abs=0.001)

    def test_growth_becomes_unrealised_gain(self):
        """Growth lifts the balance but never the basis."""
        account = TaxableAccount(balance=100_000, basis=100_000)
        account.grow(1.10)
        assert account.basis == pytest.approx(100_000)
        assert account.gain_fraction == pytest.approx(10_000 / 110_000)

    def test_deposits_add_to_basis(self):
        """New money is not gain, so it dilutes the taxable fraction."""
        account = TaxableAccount(balance=100_000, basis=50_000)
        account.deposit(50_000)
        assert account.balance == pytest.approx(150_000)
        assert account.basis == pytest.approx(100_000)
        assert account.gain_fraction == pytest.approx(50_000 / 150_000)

    def test_final_withdrawal_is_capped_by_the_balance(self):
        """Draining a portfolio nets less than asked, leaving a shortfall."""
        account = TaxableAccount(balance=1_000, basis=500)
        net, tax = account.withdraw_net(5_000)
        assert account.balance == 0.0
        assert net == pytest.approx(875.0)
        assert tax == pytest.approx(125.0)

    def test_lifo_sells_the_newest_lot_first(self):
        """A sale right after a deposit is almost untaxed under LIFO."""
        portfolio = Portfolio(balance=0, lot_method=LotMethod.LIFO)
        account = TaxableAccount.from_portfolio(portfolio)
        account.deposit(10_000)
        account.grow(1.10)
        account.deposit(10_000)          # newest lot: bought at par, no gain
        net, tax = account.withdraw_net(5_000)
        assert tax == 0.0
        assert net == pytest.approx(5_000)

    def test_fifo_sells_the_oldest_lot_first(self):
        """The same sale under FIFO hits the grown lot and is taxed."""
        portfolio = Portfolio(balance=0, lot_method=LotMethod.FIFO)
        account = TaxableAccount.from_portfolio(portfolio)
        account.deposit(10_000)
        account.grow(1.10)               # oldest lot now 11,000 on a 10,000 basis
        account.deposit(10_000)
        net, tax = account.withdraw_net(5_000)
        assert tax > 0
        assert net == pytest.approx(5_000)

    def test_synthetic_history_reproduces_the_stated_profit_fraction(self):
        """An opening balance is expanded into lots that net to what was typed."""
        portfolio = Portfolio(balance=1_500_000, profit_fraction_pct=50,
                              lot_method=LotMethod.FIFO)
        account = TaxableAccount.from_portfolio(portfolio)
        assert sum(lot.value for lot in account.lots) == pytest.approx(1_500_000)
        assert sum(lot.basis for lot in account.lots) == pytest.approx(750_000, rel=1e-3)
        # Oldest lot carries the most gain, newest almost none.
        assert account.lots[0].gain_fraction > account.lots[-1].gain_fraction
        # The newest lot is essentially at par; the residual is the rescale that
        # corrects for `count` being a rounded solution of a continuous equation.
        assert account.lots[-1].gain_fraction < 0.01

    def test_opening_basis_comes_from_the_profit_fraction(self):
        """A portfolio declared 90% profit starts with 10% basis."""
        account = TaxableAccount.from_portfolio(
            Portfolio(balance=200_000, profit_fraction_pct=90))
        assert account.basis == pytest.approx(20_000)
        assert account.gain_fraction == pytest.approx(0.9)
