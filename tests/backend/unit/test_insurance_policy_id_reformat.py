"""Regression tests for provider-side policy-ID reformatting.

In September 2026 HaPhoenix restyled the parenthesised internal ID appended to
Keren Hishtalmut policy numbers (``"007-916-407357 (8296857)"`` ->
``"007-916-407357 (08296857)"``). Nothing about the accounts changed, but
every identity lookup was an exact string match, so the next scrape forked a
second insurance account and a second investment — double-counting the KH
balance in net worth. These tests pin the reformat-insensitive matching that
prevents a repeat.
"""

from backend.constants.categories import INVESTMENTS_CATEGORY
from backend.repositories.insurance_account_repository import (
    InsuranceAccountRepository,
)
from backend.repositories.investments_repository import InvestmentsRepository
from backend.services.investments_service import InvestmentsService

OLD_ID = "007-916-407357 (8296857)"
RESTYLED_ID = "007-916-407357 (08296857)"
CANONICAL = "007-916-407357"


def _kh_meta(policy_id, **overrides):
    """Return scraped hishtalmut metadata for ``policy_id``."""
    meta = {
        "policy_type": "hishtalmut",
        "policy_id": policy_id,
        "provider": "hafenix",
        "account_name": "קרן השתלמות",
        "balance": 57110.0,
        "balance_date": "2026-08-18",
        "commission_deposits_pct": 1.0,
        "commission_savings_pct": 0.5,
        "liquidity_date": "2027-04-01",
    }
    meta.update(overrides)
    return meta


class TestInsuranceAccountLookupAcrossReformat:
    """Tests for ``InsuranceAccountRepository.get_by_policy_id``."""

    def test_restyled_policy_id_finds_the_stored_account(self, db_session):
        """Verify a reformatted ID matches the account stored under the old one."""
        repo = InsuranceAccountRepository(db_session)
        repo.upsert(
            provider="hafenix",
            policy_id=CANONICAL,
            policy_type="hishtalmut",
            account_name="קרן השתלמות",
            balance=57110.0,
            balance_date="2026-08-18",
        )

        found = repo.get_by_policy_id(RESTYLED_ID)

        assert found is not None
        assert found.policy_id == CANONICAL

    def test_upsert_under_a_restyled_id_updates_rather_than_forks(self, db_session):
        """Verify a rescrape refreshes the existing row and keeps its policy ID."""
        repo = InsuranceAccountRepository(db_session)
        repo.upsert(
            provider="hafenix",
            policy_id=CANONICAL,
            policy_type="hishtalmut",
            account_name="קרן השתלמות",
            balance=57110.0,
            balance_date="2026-08-18",
        )

        repo.upsert(
            provider="hafenix",
            policy_id=RESTYLED_ID,
            policy_type="hishtalmut",
            account_name="קרן השתלמות",
            balance=56957.0,
            balance_date="2026-08-30",
        )

        accounts = repo.get_all()
        assert len(accounts) == 1
        assert accounts[0].policy_id == CANONICAL
        assert accounts[0].balance == 56957.0

    def test_a_different_policy_still_creates_its_own_account(self, db_session):
        """Verify normalization does not merge genuinely distinct policies."""
        repo = InsuranceAccountRepository(db_session)
        repo.upsert(
            provider="hafenix",
            policy_id=CANONICAL,
            policy_type="hishtalmut",
            account_name="קרן השתלמות",
            balance=57110.0,
            balance_date="2026-08-18",
        )
        repo.upsert(
            provider="hafenix",
            policy_id="007-925-053655",
            policy_type="hishtalmut",
            account_name="קרן השתלמות",
            balance=12300.0,
            balance_date="2026-08-18",
        )

        assert len(repo.get_all()) == 2


class TestInvestmentLookupAcrossReformat:
    """Tests for ``InvestmentsRepository.get_by_insurance_policy_id``."""

    def test_restyled_policy_id_finds_the_linked_investment(self, db_session):
        """Verify the fallback match locates an investment stored under the old ID."""
        repo = InvestmentsRepository(db_session)
        inv_id = repo.create_investment(
            category=INVESTMENTS_CATEGORY,
            tag=f"Keren Hishtalmut - hafenix ({CANONICAL})",
            type_="hishtalmut",
            name="קרן השתלמות",
            interest_rate_type="variable",
            insurance_policy_id=CANONICAL,
        )

        found = repo.get_by_insurance_policy_id(RESTYLED_ID)

        assert not found.empty
        assert int(found.iloc[0]["id"]) == inv_id

    def test_unknown_policy_id_still_returns_empty(self, db_session):
        """Verify the fallback does not match an unrelated policy."""
        repo = InvestmentsRepository(db_session)
        repo.create_investment(
            category=INVESTMENTS_CATEGORY,
            tag=f"Keren Hishtalmut - hafenix ({CANONICAL})",
            type_="hishtalmut",
            name="קרן השתלמות",
            interest_rate_type="variable",
            insurance_policy_id=CANONICAL,
        )

        assert repo.get_by_insurance_policy_id("007-925-053655").empty


class TestInsuranceSyncAcrossReformat:
    """Tests for ``InvestmentsService.sync_from_insurance``."""

    def test_rescrape_with_a_restyled_id_does_not_fork_an_investment(
        self, db_session
    ):
        """Verify the KH balance is not double-counted after a provider restyle."""
        service = InvestmentsService(db_session)
        service.sync_from_insurance(_kh_meta(CANONICAL))

        service.sync_from_insurance(
            _kh_meta(RESTYLED_ID, balance=56957.0, balance_date="2026-08-30")
        )

        investments = service.investments_repo.get_all_investments()
        hishtalmut = investments[investments["type"] == "hishtalmut"]
        assert len(hishtalmut) == 1
        assert hishtalmut.iloc[0]["insurance_policy_id"] == CANONICAL

    def test_matched_investment_keeps_its_stored_policy_id_in_the_tag(
        self, db_session
    ):
        """Verify the tag tracks the stored ID, which other tables join on."""
        service = InvestmentsService(db_session)
        service.sync_from_insurance(_kh_meta(CANONICAL))

        service.sync_from_insurance(_kh_meta(RESTYLED_ID))

        investments = service.investments_repo.get_all_investments()
        hishtalmut = investments[investments["type"] == "hishtalmut"]
        assert hishtalmut.iloc[0]["tag"] == f"Keren Hishtalmut - hafenix ({CANONICAL})"

    def test_both_scrapes_snapshot_onto_the_same_investment(self, db_session):
        """Verify each scrape's balance lands on one investment, not two."""
        service = InvestmentsService(db_session)
        service.sync_from_insurance(_kh_meta(CANONICAL))
        service.sync_from_insurance(
            _kh_meta(RESTYLED_ID, balance=56957.0, balance_date="2026-08-30")
        )

        investments = service.investments_repo.get_all_investments()
        inv_id = int(
            investments[investments["type"] == "hishtalmut"].iloc[0]["id"]
        )
        snapshots = service.snapshots_repo.get_snapshots_for_investment(inv_id)

        assert sorted(snapshots["date"].tolist()) == ["2026-08-18", "2026-08-30"]
