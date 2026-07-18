"""Tests for InsuranceScraperAdapter._post_save_hook.

Covers the insurance-account metadata upsert, the hishtalmut → Investment
sync, and the failure-isolation guarantees (a failing sync or DB error must
never propagate out of the hook — the scrape itself already succeeded).
"""

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import select

from backend.models.insurance_account import InsuranceAccount
from backend.models.investment import Investment
from backend.models.investment_balance_snapshot import InvestmentBalanceSnapshot
from backend.scraper.adapter import InsuranceScraperAdapter

DUMMY_CREDENTIALS = {"username": "user", "password": "pass123"}
DUMMY_START_DATE = date(2026, 1, 1)


def _adapter() -> InsuranceScraperAdapter:
    """Build an insurance adapter without running the scrape lifecycle."""
    return InsuranceScraperAdapter(
        "insurance", "hafenix", "Policy Holder",
        DUMMY_CREDENTIALS, DUMMY_START_DATE, 1,
    )


def _result(*metadatas) -> SimpleNamespace:
    """Build a fake ScrapingResult with one account per metadata dict."""
    return SimpleNamespace(
        accounts=[
            SimpleNamespace(metadata=meta, transactions=[])
            for meta in metadatas
        ]
    )


def _pension_meta(**overrides) -> dict:
    """Metadata dict for a pension policy."""
    meta = {
        "provider": "hafenix",
        "policy_id": "pen-001",
        "policy_type": "pension",
        "pension_type": "makifa",
        "account_name": "Phoenix Pension",
        "balance": 150000.0,
        "balance_date": "2026-06-30",
    }
    meta.update(overrides)
    return meta


def _hishtalmut_meta(**overrides) -> dict:
    """Metadata dict for a Keren Hishtalmut policy."""
    meta = {
        "provider": "hafenix",
        "policy_id": "kh-001",
        "policy_type": "hishtalmut",
        "account_name": "Phoenix KH",
        "balance": 42000.0,
        "balance_date": "2026-06-30",
        "liquidity_date": "2027-01-01",
    }
    meta.update(overrides)
    return meta


@contextmanager
def _fake_db_context(db_session):
    """Context manager yielding the test's real in-memory session."""
    yield db_session


class TestPostSaveHookMetadataUpsert:
    """Metadata from AccountResult.metadata is persisted via upsert."""

    def test_post_save_hook_upserts_metadata_rows(self, db_session):
        """Each account's metadata dict becomes an insurance_accounts row."""
        adapter = _adapter()

        with patch(
            "backend.scraper.adapter.get_db_context",
            side_effect=lambda: _fake_db_context(db_session),
        ):
            adapter._post_save_hook(_result(_pension_meta(), _hishtalmut_meta()))

        rows = db_session.execute(select(InsuranceAccount)).scalars().all()
        by_policy = {r.policy_id: r for r in rows}
        assert set(by_policy) == {"pen-001", "kh-001"}
        assert by_policy["pen-001"].balance == 150000.0
        assert by_policy["kh-001"].liquidity_date == "2027-01-01"

    def test_post_save_hook_updates_existing_policy(self, db_session):
        """A re-scrape updates the existing row instead of duplicating it."""
        adapter = _adapter()
        db_session.add(
            InsuranceAccount(
                provider="hafenix",
                policy_id="pen-001",
                policy_type="pension",
                account_name="Phoenix Pension",
                balance=100000.0,
                balance_date="2026-05-31",
            )
        )
        db_session.commit()

        with patch(
            "backend.scraper.adapter.get_db_context",
            side_effect=lambda: _fake_db_context(db_session),
        ):
            adapter._post_save_hook(_result(_pension_meta(balance=155000.0)))

        rows = db_session.execute(select(InsuranceAccount)).scalars().all()
        assert len(rows) == 1
        assert rows[0].balance == 155000.0

    def test_post_save_hook_no_metadata_returns_early(self, db_session):
        """Accounts without metadata skip the hook entirely (no DB access)."""
        adapter = _adapter()
        mock_db_context = MagicMock()

        with patch(
            "backend.scraper.adapter.get_db_context", mock_db_context
        ):
            adapter._post_save_hook(_result(None, None))

        mock_db_context.assert_not_called()
        assert db_session.execute(select(InsuranceAccount)).scalars().all() == []


class TestPostSaveHookInvestmentSync:
    """The hishtalmut → Investment sync runs inside the hook."""

    def test_post_save_hook_syncs_hishtalmut_investment(self, db_session):
        """A hishtalmut policy creates a linked Investment + scraped snapshot."""
        adapter = _adapter()

        with patch(
            "backend.scraper.adapter.get_db_context",
            side_effect=lambda: _fake_db_context(db_session),
        ):
            adapter._post_save_hook(_result(_hishtalmut_meta()))

        investment = db_session.execute(
            select(Investment).where(Investment.insurance_policy_id == "kh-001")
        ).scalar_one()
        assert investment.name == "Phoenix KH"
        assert investment.type == "hishtalmut"
        snapshots = db_session.execute(
            select(InvestmentBalanceSnapshot).where(
                InvestmentBalanceSnapshot.investment_id == investment.id
            )
        ).scalars().all()
        assert len(snapshots) == 1
        assert snapshots[0].balance == 42000.0
        assert snapshots[0].source == "scraped"

    def test_post_save_hook_pension_does_not_create_investment(self, db_session):
        """Pension policies are metadata-only — no Investment is created."""
        adapter = _adapter()

        with patch(
            "backend.scraper.adapter.get_db_context",
            side_effect=lambda: _fake_db_context(db_session),
        ):
            adapter._post_save_hook(_result(_pension_meta()))

        assert db_session.execute(select(Investment)).scalars().all() == []
        assert len(
            db_session.execute(select(InsuranceAccount)).scalars().all()
        ) == 1


class TestPostSaveHookFailureIsolation:
    """Failures inside the hook must never propagate to the scrape flow."""

    def test_sync_failure_does_not_raise_and_metadata_survives(self, db_session):
        """A failing investment sync is logged; metadata upsert still lands."""
        adapter = _adapter()

        with patch(
            "backend.scraper.adapter.get_db_context",
            side_effect=lambda: _fake_db_context(db_session),
        ), patch(
            "backend.services.investments_service.InvestmentsService"
            ".sync_from_insurance",
            side_effect=RuntimeError("sync exploded"),
        ):
            adapter._post_save_hook(_result(_hishtalmut_meta()))  # must not raise

        rows = db_session.execute(select(InsuranceAccount)).scalars().all()
        assert [r.policy_id for r in rows] == ["kh-001"]
        assert db_session.execute(select(Investment)).scalars().all() == []

    def test_sync_failure_for_one_policy_does_not_block_others(self, db_session):
        """One policy's sync failure doesn't stop the remaining policies."""
        adapter = _adapter()
        real_sync_calls = []

        def selective_sync(self_service, meta):
            if meta["policy_id"] == "kh-bad":
                raise RuntimeError("boom")
            real_sync_calls.append(meta["policy_id"])

        with patch(
            "backend.scraper.adapter.get_db_context",
            side_effect=lambda: _fake_db_context(db_session),
        ), patch(
            "backend.services.investments_service.InvestmentsService"
            ".sync_from_insurance",
            autospec=True,
            side_effect=selective_sync,
        ):
            adapter._post_save_hook(
                _result(
                    _hishtalmut_meta(policy_id="kh-bad"),
                    _hishtalmut_meta(policy_id="kh-good"),
                )
            )

        assert real_sync_calls == ["kh-good"]
        # Both metadata rows were still saved before the sync stage.
        rows = db_session.execute(select(InsuranceAccount)).scalars().all()
        assert {r.policy_id for r in rows} == {"kh-bad", "kh-good"}

    def test_metadata_save_failure_does_not_raise(self, db_session):
        """A failure in the metadata upsert itself is swallowed and logged."""
        adapter = _adapter()

        with patch(
            "backend.scraper.adapter.get_db_context",
            side_effect=lambda: _fake_db_context(db_session),
        ), patch(
            "backend.services.insurance_account_service.InsuranceAccountService"
            ".upsert",
            side_effect=RuntimeError("db locked"),
        ):
            adapter._post_save_hook(_result(_pension_meta()))  # must not raise

        assert db_session.execute(select(InsuranceAccount)).scalars().all() == []
