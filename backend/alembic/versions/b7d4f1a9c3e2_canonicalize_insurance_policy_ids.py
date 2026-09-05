"""Canonicalize insurance policy IDs and merge the duplicates they forked.

Providers hand out policy identifiers as display strings, and HaPhoenix
reformatted its parenthesised internal ID in September 2026
(``"007-916-407357 (8296857)"`` -> ``"007-916-407357 (08296857)"``) without
any account changing. Every downstream identity is derived from that string,
so the reformat forked a second insurance account, a second Keren Hishtalmut
investment (double-counting its balance in net worth) and a second copy of
the entire scraped deposit history.

This migration strips the volatile parenthesised suffix from stored policy
IDs, rewrites scraped transaction dedup keys to the reformat-insensitive key,
and merges every group that collapses onto the same key — keeping the oldest
row of each group so user edits and any rows referencing it survive.

The normalization is inlined rather than imported from
``scraper.utils.policy_ids`` so this migration stays a fixed snapshot, per
Alembic convention.

Revision ID: b7d4f1a9c3e2
Revises: a3e5c7b9d1f4
Create Date: 2026-09-05
"""

import re
from collections import defaultdict

import sqlalchemy as sa
from alembic import op

revision = "b7d4f1a9c3e2"
down_revision = "a3e5c7b9d1f4"
branch_labels = None
depends_on = None

_PAREN_SUFFIX_RE = re.compile(r"\s*\([^()]*\)\s*$")
_DIGIT_RUN_RE = re.compile(r"\d+")


def _normalize_policy_id(raw):
    """Drop a trailing parenthesised internal ID; keep leading zeros."""
    if raw is None:
        return ""
    value = str(raw).strip()
    stripped = _PAREN_SUFFIX_RE.sub("", value).strip()
    return stripped or value


def _policy_id_key(value):
    """Normalize, then strip insignificant leading zeros from each digit run."""
    normalized = _normalize_policy_id(value)
    if not normalized:
        return ""
    return _DIGIT_RUN_RE.sub(
        lambda m: m.group(0).lstrip("0") or "0", normalized
    ).casefold()


def _table_exists(bind, name):
    return name in sa.inspect(bind).get_table_names()


def _merge_insurance_accounts(bind):
    """Collapse accounts whose policy IDs share a key; keep the oldest row."""
    rows = bind.execute(
        sa.text(
            "SELECT id, policy_id, balance, balance_date, custom_name "
            "FROM insurance_accounts ORDER BY id"
        )
    ).mappings().all()

    groups = defaultdict(list)
    for row in rows:
        key = _policy_id_key(row["policy_id"])
        if key:
            groups[key].append(row)

    for group in groups.values():
        keeper = group[0]
        # The freshest scrape wins on balance; the oldest row wins on identity
        # and on any name the user typed.
        freshest = max(group, key=lambda r: (r["balance_date"] or "", r["id"]))
        custom_name = next((r["custom_name"] for r in group if r["custom_name"]), None)
        bind.execute(
            sa.text(
                "UPDATE insurance_accounts SET policy_id = :pid, balance = :bal, "
                "balance_date = :bdate, custom_name = :cname WHERE id = :id"
            ),
            {
                "pid": _normalize_policy_id(keeper["policy_id"]),
                "bal": freshest["balance"],
                "bdate": freshest["balance_date"],
                "cname": custom_name,
                "id": keeper["id"],
            },
        )
        for loser in group[1:]:
            bind.execute(
                sa.text("DELETE FROM insurance_accounts WHERE id = :id"),
                {"id": loser["id"]},
            )


def _merge_investments(bind):
    """Collapse insurance-linked investments; move the losers' snapshots over."""
    rows = bind.execute(
        sa.text(
            "SELECT id, category, tag, insurance_policy_id FROM investments "
            "WHERE insurance_policy_id IS NOT NULL AND insurance_policy_id != '' "
            "ORDER BY id"
        )
    ).mappings().all()

    groups = defaultdict(list)
    for row in rows:
        key = _policy_id_key(row["insurance_policy_id"])
        if key:
            groups[key].append(row)

    for group in groups.values():
        keeper = group[0]
        canonical = _normalize_policy_id(keeper["insurance_policy_id"])

        for loser in group[1:]:
            # Snapshots are (investment_id, date)-unique: hand over only the
            # dates the keeper is missing, then drop the rest with the loser.
            bind.execute(
                sa.text(
                    "UPDATE investment_balance_snapshots SET investment_id = :keep "
                    "WHERE investment_id = :lose AND date NOT IN "
                    "(SELECT date FROM investment_balance_snapshots "
                    " WHERE investment_id = :keep)"
                ),
                {"keep": keeper["id"], "lose": loser["id"]},
            )
            bind.execute(
                sa.text(
                    "DELETE FROM investment_balance_snapshots WHERE investment_id = :lose"
                ),
                {"lose": loser["id"]},
            )
            bind.execute(
                sa.text("DELETE FROM investments WHERE id = :id"), {"id": loser["id"]}
            )

        # Retag only after the duplicates are gone — investments is
        # UNIQUE(category, tag).
        new_tag = keeper["tag"].replace(keeper["insurance_policy_id"], canonical)
        if new_tag != keeper["tag"]:
            bind.execute(
                sa.text(
                    "UPDATE manual_investment_transactions SET tag = :new "
                    "WHERE category = :cat AND tag = :old"
                ),
                {"new": new_tag, "cat": keeper["category"], "old": keeper["tag"]},
            )
        bind.execute(
            sa.text(
                "UPDATE investments SET tag = :tag, insurance_policy_id = :pid "
                "WHERE id = :id"
            ),
            {"tag": new_tag, "pid": canonical, "id": keeper["id"]},
        )


def _rekey_insurance_transactions(bind):
    """Rewrite scraped dedup IDs to the policy key, then drop the duplicates."""
    rows = bind.execute(
        sa.text(
            "SELECT unique_id, id, account_number FROM insurance_transactions "
            "ORDER BY unique_id"
        )
    ).mappings().all()

    for row in rows:
        account_number = row["account_number"] or ""
        if not account_number:
            continue
        canonical = _normalize_policy_id(account_number)
        key = _policy_id_key(account_number)
        # The scraper builds the identifier as "<policy>_<date>_<amount>".
        # Swap the prefix rather than rebuilding it, so the float formatting in
        # the suffix is preserved byte-for-byte.
        new_id = row["id"]
        if new_id and new_id.startswith(account_number):
            new_id = key + new_id[len(account_number) :]
        if new_id == row["id"] and canonical == account_number:
            continue
        bind.execute(
            sa.text(
                "UPDATE insurance_transactions SET id = :new_id, "
                "account_number = :acct WHERE unique_id = :uid"
            ),
            {"new_id": new_id, "acct": canonical, "uid": row["unique_id"]},
        )

    # Rows that now collide on the scraped dedup key are the same deposit
    # reported twice. Keep the oldest — it carries any category/tag the user
    # assigned, and savings-goal links and refunds already point at it.
    bind.execute(
        sa.text(
            "DELETE FROM insurance_transactions WHERE unique_id NOT IN ("
            "  SELECT MIN(unique_id) FROM insurance_transactions"
            "  GROUP BY id, provider, date, amount"
            ")"
        )
    )


def upgrade() -> None:
    """Canonicalize policy IDs and merge the rows a reformat forked."""
    bind = op.get_bind()
    if _table_exists(bind, "insurance_accounts"):
        _merge_insurance_accounts(bind)
    if _table_exists(bind, "investments") and _table_exists(
        bind, "investment_balance_snapshots"
    ):
        _merge_investments(bind)
    if _table_exists(bind, "insurance_transactions"):
        _rekey_insurance_transactions(bind)


def downgrade() -> None:
    """No-op.

    The merge is not reversible: the duplicate rows a provider's reformat
    forked are deleted, and the policy ID they were keyed by is gone with
    them. Downgrading leaves the canonicalized data in place, which every
    earlier revision reads correctly.
    """
