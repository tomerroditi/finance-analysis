"""Tests for HaPhoenix policy-ID handling in the deposit builders.

HaPhoenix restyled the parenthesised internal ID it appends to Keren
Hishtalmut policy numbers in September 2026. Deposit dedup identifiers are
built from the policy ID, so the restyle made every historical deposit look
new and the whole history was re-inserted. The builders now key on the
reformat-insensitive policy key instead.
"""

from scraper.providers.insurances.hafenix import HaPhoenixScraper
from scraper.utils.policy_ids import policy_id_key

OLD_ID = "007-916-407357 (8296857)"
RESTYLED_ID = "007-916-407357 (08296857)"

_HISHTALMUT_DETAIL = {
    "deposits": {
        "list": [
            {
                "list": [
                    {
                        "depositDate": "12.01.2026",
                        "totalDeposit": 1571.0,
                        "employerName": "Acme",
                        "employeeDeposit": 400.0,
                        "employerDeposit": 1171.0,
                    }
                ]
            }
        ]
    }
}


def _identifiers(policy_id: str) -> list[str]:
    """Build hishtalmut deposits for ``policy_id`` and return their dedup IDs."""
    scraper = HaPhoenixScraper.__new__(HaPhoenixScraper)
    transactions = scraper._build_hishtalmut_deposits(
        policy_id_key(policy_id), _HISHTALMUT_DETAIL
    )
    return [txn.identifier for txn in transactions]


class TestHaPhoenixDepositIdentifiers:
    """Tests for deposit dedup identifiers across a policy-ID restyle."""

    def test_deposit_identifier_survives_the_provider_restyle(self):
        """Verify both spellings of one policy produce the same dedup ID."""
        assert _identifiers(OLD_ID) == _identifiers(RESTYLED_ID)

    def test_identifier_drops_the_volatile_internal_id(self):
        """Verify the parenthesised suffix never reaches the dedup key."""
        identifiers = _identifiers(RESTYLED_ID)

        assert identifiers == ["7-916-407357_2026-01-12_1571.0"]

    def test_distinct_policies_keep_distinct_identifiers(self):
        """Verify deposits from different policies are not deduped together."""
        assert _identifiers(OLD_ID) != _identifiers("007-925-053655 (9527977)")
