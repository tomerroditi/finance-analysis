"""Tests for the logic ported from upstream israeli-bank-scrapers (2026-07).

Covers the four upstream changes synced in this pass:

* ``d555d97`` isracard bot-detection workaround — the shared in-page fetch
  helpers now surface anti-automation blocks as explicit errors.
* ``cba9737`` max credit-card balances — derived from the home-page card
  summary rather than the transactions feed.
* ``70e4018`` visa-cal frame completion — cards resolve against both the
  bank-issued and Cal-issued frame groups.
* ``de14046`` leumi savings accounts — deposits become balance-only accounts.
"""

import asyncio

import pytest

from scraper.exceptions import ScraperError
from scraper.models.account import CardType
from scraper.providers.banks.leumi import _fetch_savings_for_account
from scraper.providers.credit_cards.max import (
    _get_card_balance,
    _get_card_balance_date,
)
from scraper.providers.credit_cards.visa_cal import _resolve_card_frame
from scraper.utils import fetch, waiting


class _FakePage:
    """Minimal Page stand-in whose ``evaluate`` returns a canned payload."""

    def __init__(self, payload):
        self._payload = payload

    async def evaluate(self, _js, _arg=None):
        return self._payload


class TestAutomationBlockDetection:
    """In-page fetches raise when the provider blocks automated access."""

    def test_429_status_raises_scraper_error(self):
        """A 429 response is reported as an automation block, not parsed."""
        page = _FakePage({"__data": "slow down", "__status": 429})

        with pytest.raises(ScraperError) as excinfo:
            asyncio.run(fetch.fetch_get_within_page(page, "https://x/y"))

        assert "Automation detected and blocked" in str(excinfo.value)

    def test_bot_detection_body_raises_scraper_error(self):
        """A 200 whose body names the detector is still treated as a block."""
        page = _FakePage(
            {"__data": "<html>Bot detection triggered</html>", "__status": 200}
        )

        with pytest.raises(ScraperError) as excinfo:
            asyncio.run(fetch.fetch_post_within_page(page, "https://x/y", {}))

        assert "Automation detected and blocked" in str(excinfo.value)

    def test_ignore_errors_suppresses_the_block_error(self):
        """Callers opting out of errors get None rather than a raised block."""
        page = _FakePage({"__data": "block automation", "__status": 429})

        result = asyncio.run(
            fetch.fetch_get_within_page(page, "https://x/y", ignore_errors=True)
        )

        assert result is None

    def test_ordinary_json_response_is_unaffected(self):
        """A normal 200 JSON body still parses as before."""
        page = _FakePage({"__data": '{"ok": true}', "__status": 200})

        assert asyncio.run(fetch.fetch_get_within_page(page, "https://x/y")) == {
            "ok": True
        }


class TestRandomDelay:
    """random_delay jitters the pause between rate-limited requests."""

    def test_delay_stays_within_bounds(self, monkeypatch):
        """The sleep duration falls inside the requested range."""
        slept: list[float] = []

        async def fake_sleep(seconds):
            slept.append(seconds)

        monkeypatch.setattr(waiting.asyncio, "sleep", fake_sleep)
        asyncio.run(waiting.random_delay(2.5, 3.0))

        assert len(slept) == 1
        assert 2.5 <= slept[0] <= 3.0


class TestMaxCardBalance:
    """Max card balances derive from the credit limit and remaining headroom."""

    def test_balance_is_negative_spend_against_the_limit(self):
        """Spent = limit - headroom, returned negative per the sign convention."""
        assert _get_card_balance({"CreditLimit": 10000, "OpenToBuy": 2500.005}) == -7499.99

    def test_balance_is_none_when_a_component_is_missing(self):
        """A card without both figures reports no balance rather than guessing."""
        assert _get_card_balance({"CreditLimit": 10000, "OpenToBuy": None}) is None
        assert _get_card_balance({"CreditLimit": None, "OpenToBuy": 2500}) is None

    def test_balance_date_picks_the_shekel_cycle_entry(self):
        """The shekel cycle entry supplies the balance date, not the first row."""
        card = {
            "CycleSummary": [
                {"CurrencySymbol": "$", "Date": "2026-07-01"},
                {"CurrencySymbol": "₪", "Date": "2026-07-10"},
            ]
        }

        assert _get_card_balance_date(card) == "2026-07-10"

    def test_balance_date_is_none_without_a_shekel_entry(self):
        """A card with no shekel cycle reports no balance date."""
        assert _get_card_balance_date({"CycleSummary": []}) is None


class TestVisaCalFrameResolution:
    """Visa Cal cards resolve against whichever frame group holds them."""

    def test_bank_issued_card_is_found_and_typed(self):
        """A card in bankIssuedCards is typed BANK_ISSUED with its own frame."""
        response = {
            "result": {
                "bankIssuedCards": {
                    "cardLevelFrames": [{"cardUniqueId": "A", "nextTotalDebit": 120}],
                    "frameLimitForCardAmount": 9000,
                },
                "calIssuedCards": {"cardLevelFrames": []},
            }
        }

        frame, card_type, group = _resolve_card_frame(response, "A")

        assert frame == {"cardUniqueId": "A", "nextTotalDebit": 120}
        assert card_type is CardType.BANK_ISSUED
        assert group["frameLimitForCardAmount"] == 9000

    def test_cal_issued_card_is_found_and_typed(self):
        """A card only in calIssuedCards is typed COMPANY_ISSUED."""
        response = {
            "result": {
                "bankIssuedCards": {"cardLevelFrames": []},
                "calIssuedCards": {
                    "cardLevelFrames": [{"cardUniqueId": "B", "nextTotalDebit": 55}],
                },
            }
        }

        frame, card_type, _group = _resolve_card_frame(response, "B")

        assert frame == {"cardUniqueId": "B", "nextTotalDebit": 55}
        assert card_type is CardType.COMPANY_ISSUED

    def test_missing_card_falls_back_to_the_cal_issued_group(self):
        """With no card-level frame, the Cal-issued account totals still apply."""
        response = {
            "result": {"calIssuedCards": {"nextTotalDebitForAccount": 300}}
        }

        frame, card_type, group = _resolve_card_frame(response, "missing")

        assert frame is None
        assert card_type is CardType.COMPANY_ISSUED
        assert group["nextTotalDebitForAccount"] == 300

    def test_empty_response_does_not_raise(self):
        """An empty frames payload yields no frame and an empty group."""
        assert _resolve_card_frame({}, "A") == (None, CardType.COMPANY_ISSUED, {})


class TestLeumiSavingsAccounts:
    """Leumi deposits surface as balance-only savings accounts."""

    def test_each_deposit_becomes_its_own_account(self, monkeypatch):
        """Deposits map to `<account>-<depositId>` accounts carrying balances."""

        async def fake_fetch(_page, _url, ignore_errors=False):
            return {
                "depositsAndSavingsItems": [
                    {"depositId": "77", "currentBalance": 15000.5},
                    {"depositId": "88", "currentBalance": 240},
                ]
            }

        monkeypatch.setattr(
            "scraper.providers.banks.leumi.fetch_get_within_page", fake_fetch
        )

        accounts = asyncio.run(_fetch_savings_for_account(None, "123456"))

        assert [a.account_number for a in accounts] == ["123456-77", "123456-88"]
        assert [a.balance for a in accounts] == [15000.5, 240]
        assert all(a.savings_account for a in accounts)
        assert all(a.transactions == [] for a in accounts)

    def test_no_deposits_yields_no_accounts(self, monkeypatch):
        """An account without savings contributes nothing."""

        async def fake_fetch(_page, _url, ignore_errors=False):
            return {"depositsAndSavingsItems": []}

        monkeypatch.setattr(
            "scraper.providers.banks.leumi.fetch_get_within_page", fake_fetch
        )

        assert asyncio.run(_fetch_savings_for_account(None, "123456")) == []

    def test_fetch_failure_is_swallowed(self, monkeypatch):
        """A failing deposits endpoint must not fail the whole Leumi scrape."""

        async def fake_fetch(_page, _url, ignore_errors=False):
            raise RuntimeError("endpoint gone")

        monkeypatch.setattr(
            "scraper.providers.banks.leumi.fetch_get_within_page", fake_fetch
        )

        assert asyncio.run(_fetch_savings_for_account(None, "123456")) == []
