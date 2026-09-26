"""Rule-based transaction tagging: rule CRUD, conflict detection and application.

Also hosts the credit-card bill auto-tagger, which matches bank debits to the
monthly total of each known card.
"""

import json
import logging
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.tables import Tables, TransactionsTableFields
from backend.errors import (
    BadRequestException,
    EntityNotFoundException,
    ValidationException,
)
from backend.repositories.tagging_rule_match_repository import (
    TaggingRuleMatchRepository,
)
from backend.repositories.tagging_rules_repository import TaggingRulesRepository
from backend.repositories.transactions import TransactionsRepository
from backend.services.tagging_service import CategoriesTagsService
from backend.services.transactions_service import TransactionsService

# Fields a condition may match on, and the operators each accepts.
TEXT_CONDITION_FIELDS: list[str] = [
    "description",
    "account_name",
    "provider",
    "service",
]
NUMERIC_CONDITION_FIELDS: list[str] = ["amount"]
VALID_TEXT_OPERATORS: list[str] = ["contains", "equals", "starts_with", "ends_with"]
VALID_NUMERIC_OPERATORS: list[str] = ["gt", "lt", "gte", "lte", "equals", "between"]
# ``service`` is not a column: it selects which transaction table(s) a rule
# runs against, so it only makes sense with ``equals`` and one of these values.
VALID_SERVICE_VALUES: set[str] = {"bank", "credit_card"}

logger = logging.getLogger(__name__)


class TaggingRulesService:
    """
    Service for managing rule-based tagging operations with recursive logic.

    Rules are stored as recursive condition trees (``AND``/``OR`` groups and
    ``CONDITION`` leaves). The service supports creating, updating, deleting,
    applying, and previewing rules across ``credit_card_transactions`` and
    ``bank_transactions`` tables. Conflict detection prevents overlapping rules
    that would assign different category/tag pairs to the same transactions.

    Rules have no priority: they are evaluated in creation order (``id``
    ascending) and the first rule that matches a transaction wins. Overlaps
    are blocked at creation time by ``check_conflicts``, so ordering only
    matters for transactions that arrive later and happen to match several
    rules.

    Parameters
    ----------
    db : Session
        SQLAlchemy session for database operations.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.rules_repo = TaggingRulesRepository(db)
        self.match_repo = TaggingRuleMatchRepository(db)
        self.transactions_repo = TransactionsRepository(db)
        self.categories_tags_service = CategoriesTagsService(db)
        self.transactions_service = TransactionsService(db)

    def get_all_rules(self) -> pd.DataFrame:
        """
        Get all tagging rules.

        Returns
        -------
        pd.DataFrame
            All rules in creation order (``id`` ascending) with columns
            ``id``, ``name``, ``conditions``, ``category``, ``tag``,
            ``created_at`` and ``updated_at``.
        """
        return self.rules_repo.get_all_rules()

    def _validate_target(self, category: Any, tag: Any) -> None:
        """
        Ensure a rule's target category/tag pair exists.

        A rule that assigns a category or tag the categories table does not
        know about would tag transactions with values no UI can display or
        budget, so the pair must already exist before a rule may use it.

        Parameters
        ----------
        category : Any
            Category the rule assigns.
        tag : Any
            Tag the rule assigns; must belong to ``category``.

        Raises
        ------
        BadRequestException
            If either value is blank or the pair is not a known category/tag.
        """
        if not isinstance(category, str) or not category.strip():
            raise BadRequestException("Rule category must not be blank")
        if not isinstance(tag, str) or not tag.strip():
            raise BadRequestException("Rule tag must not be blank")

        categories = self.categories_tags_service.get_categories_and_tags()
        if category not in categories:
            raise BadRequestException(f"Unknown category '{category}'")
        if tag not in categories[category]:
            raise BadRequestException(
                f"Tag '{tag}' does not exist under category '{category}'"
            )

    def add_rule(
        self,
        name: str,
        conditions: dict[str, Any],
        category: str,
        tag: str,
    ) -> tuple[int, int]:
        """
        Add a new tagging rule with integrity and conflict checks.

        Validates the condition structure, checks for conflicts with existing
        rules, persists the rule, and immediately applies it to matching
        untagged transactions.

        Parameters
        ----------
        name : str
            Human-readable name for the rule.
        conditions : dict
            Recursive condition tree (``AND``/``OR``/``CONDITION`` nodes).
        category : str
            Category to assign to matching transactions.
        tag : str
            Tag to assign to matching transactions.

        Returns
        -------
        tuple[int, int]
            ``(rule_id, n_tagged)`` where ``rule_id`` is the new rule's ID
            and ``n_tagged`` is the number of transactions immediately tagged.

        Raises
        ------
        BadRequestException
            If condition validation or conflict checking fails, or the
            category/tag pair does not exist.
        """
        self.validate_rule_integrity(conditions)
        self._validate_target(category, tag)
        self.check_conflicts(conditions, category, tag)

        rule_id = self.rules_repo.add_rule(
            name=name,
            conditions=conditions,
            category=category,
            tag=tag,
        )
        n_tagged = self.apply_rule_by_id(rule_id)
        return rule_id, n_tagged

    def _normalize_conditions(self, conditions: Any) -> dict[str, Any]:
        """
        Normalize legacy condition formats to the recursive dict format.

        - List format: ``[...]`` -> ``{"type": "AND", "subconditions": [...]}``
        - Simple dict: ``{"field": ...}`` -> ``{"type": "CONDITION", ...}``
        - Recursive dict: ``{"type": "AND", "subconditions": [...]}`` (unchanged)

        Parameters
        ----------
        conditions : Any
            Condition tree in any supported format, or its JSON string.

        Returns
        -------
        dict[str, Any]
            The recursive condition tree.

        Raises
        ------
        ValueError
            If ``conditions`` is a string that is not valid JSON. Such a rule
            is broken; callers that iterate stored rules skip it rather than
            guess at what it meant (e.g. by rewriting it into a
            ``description contains "<garbage>"`` match).
        """
        if isinstance(conditions, str):
            try:
                conditions = json.loads(conditions)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"Rule conditions are not valid JSON: {conditions!r}"
                ) from exc

        if isinstance(conditions, list):
            # Legacy list of conditions -> AND group
            return {
                "type": "AND",
                "subconditions": [self._normalize_conditions(c) for c in conditions],
            }

        if isinstance(conditions, dict):
            if "type" in conditions:
                if conditions["type"] in ["AND", "OR"]:
                    conditions["subconditions"] = [
                        self._normalize_conditions(c)
                        for c in conditions.get("subconditions", [])
                    ]
                return conditions
            return {
                "type": "CONDITION",
                "field": conditions.get("field", "description"),
                "operator": conditions.get("operator", "contains"),
                "value": conditions.get("value", ""),
            }

        return {
            "type": "CONDITION",
            "field": "description",
            "operator": "contains",
            "value": "",
        }

    def update_rule(self, rule_id: int, **kwargs: Any) -> int:
        """
        Update an existing tagging rule with validation and conflict checks.

        After updating, the rule is re-applied: untagged transactions that
        match it are tagged, and — when the rule's category or tag changed —
        transactions that still carry the rule's *previous* category/tag and
        match the (possibly new) conditions are moved to the new pair.
        Transactions tagged with anything else are never touched.

        Parameters
        ----------
        rule_id : int
            ID of the rule to update.
        **kwargs
            Fields to update (e.g. ``name``, ``conditions``, ``category``, ``tag``).

        Returns
        -------
        int
            Number of transactions tagged or re-tagged by the updated rule.

        Raises
        ------
        EntityNotFoundException
            If no rule with ``rule_id`` exists.
        BadRequestException
            If condition validation or conflict checking fails, or the new
            category/tag pair does not exist.
        """
        rule = self.rules_repo.get_rule_by_id(rule_id)
        if not rule:
            raise EntityNotFoundException(f"Rule {rule_id} not found")

        old_category, old_tag = rule.category, rule.tag

        new_conditions = kwargs.get("conditions", rule.conditions)
        new_category = kwargs.get("category", old_category)
        new_tag = kwargs.get("tag", old_tag)

        if "conditions" in kwargs:
            self.validate_rule_integrity(new_conditions)
        if "category" in kwargs or "tag" in kwargs:
            self._validate_target(new_category, new_tag)

        self.check_conflicts(
            new_conditions, new_category, new_tag, exclude_rule_id=rule_id
        )

        if not self.rules_repo.update_rule(rule_id, **kwargs):
            return 0

        previous = None
        if (new_category, new_tag) != (old_category, old_tag):
            previous = (old_category, old_tag)
        rule_dict = {
            "id": rule_id,
            "conditions": new_conditions,
            "category": new_category,
            "tag": new_tag,
        }
        return len(self._apply_single_rule_returning_ids(rule_dict, previous=previous))

    def delete_rule(self, rule_id: int) -> bool:
        """
        Delete a tagging rule.

        Parameters
        ----------
        rule_id : int
            ID of the rule to delete.

        Returns
        -------
        bool
            ``True`` if the rule was deleted.

        Raises
        ------
        EntityNotFoundException
            If no rule with ``rule_id`` exists.
        """
        success = self.rules_repo.delete_rule(rule_id)
        if not success:
            raise EntityNotFoundException(f"Rule {rule_id} not found")
        return success

    def apply_rules(self, overwrite: bool = False) -> int:
        """
        Apply all tagging rules to matching transactions.

        Rules are applied in creation order (``id`` ascending) and the first
        rule to claim a transaction wins: a transaction tagged by an earlier
        rule in this run is skipped by every later rule, in both modes.
        Rules whose stored conditions cannot be parsed are skipped and logged.

        Parameters
        ----------
        overwrite : bool, optional
            When ``True``, every transaction matching a rule is (re)tagged
            with that rule's category/tag, whatever it carried before — the
            tables keep no record of whether a tag was set by a rule or by
            hand, so ``overwrite`` means "reset every matching transaction to
            what the rules say". Default is ``False`` (only untagged rows).

        Returns
        -------
        int
            Total number of unique transactions that were tagged or re-tagged.
        """
        rules = self.rules_repo.get_all_rules().to_dict(orient="records")

        # ``claimed`` is every pair some rule *matched* — a rule owns a
        # transaction even when it had nothing to change about it, otherwise a
        # later overlapping rule would steal the rows the first rule already
        # agrees with. ``modified`` is the subset actually written, which is
        # what the caller counts.
        claimed: set[tuple[str, int]] = set()
        modified: set[tuple[str, int]] = set()
        for rule in rules:
            modified |= self._apply_single_rule_returning_ids(
                rule, overwrite=overwrite, claimed=claimed
            )

        self.transactions_service.realign_closed_investments()
        return len(modified)

    def apply_rule_by_id(self, rule_id: int, overwrite: bool = False) -> int:
        """
        Apply a single tagging rule to matching transactions.

        Parameters
        ----------
        rule_id : int
            ID of the rule to apply.
        overwrite : bool, optional
            When ``True``, re-tags transactions that already have a different
            category/tag. Default is ``False``.

        Returns
        -------
        int
            Number of transactions tagged.

        Raises
        ------
        EntityNotFoundException
            If no rule with ``rule_id`` exists.
        """
        rule = self.rules_repo.get_rule_by_id(rule_id)
        if not rule:
            raise EntityNotFoundException(f"Rule {rule_id} not found")
        rule_dict = {
            "id": rule.id,
            "conditions": rule.conditions,
            "category": rule.category,
            "tag": rule.tag,
        }
        count = len(
            self._apply_single_rule_returning_ids(rule_dict, overwrite=overwrite)
        )
        self.transactions_service.realign_closed_investments()
        return count

    def preview_rule(
        self, conditions: dict[str, Any], limit: int | None = None
    ) -> list[dict[str, Any]]:
        """
        Preview which transactions would match given conditions, without writing.

        Parameters
        ----------
        conditions : dict
            Condition tree to evaluate.
        limit : int, optional
            Maximum number of matches to return; ``None`` returns all.

        Returns
        -------
        list[dict]
            Matching transactions (key fields plus ``source``), newest first.
        """
        conditions = self._normalize_conditions(conditions)
        tables = self._get_tables_names_for_conditions(conditions)

        results = []
        for table in tables:
            df = self.match_repo.preview(table, conditions, limit)
            if not df.empty:
                df["source"] = table
                results.append(df)

        if not results:
            return []

        combined = pd.concat(results, ignore_index=True)
        combined = combined.sort_values("date", ascending=False)
        if limit is not None:
            combined = combined.head(limit)
        return combined.to_dict(orient="records")

    def validate_rule_integrity(self, conditions: dict[str, Any]) -> None:
        """
        Validate a condition tree's fields, operators and values.

        Every group needs subconditions, every leaf a known field, an operator
        valid for that field's type, and a value of the right shape (numeric
        for ``amount``, a known service for ``service``, non-blank text
        otherwise).

        Parameters
        ----------
        conditions : dict
            Condition tree to validate.

        Raises
        ------
        BadRequestException
            If any node is malformed.
        ValidationException
            If a value cannot even be coerced for checking (e.g. ``null`` in a
            numeric comparison, or conditions that are not valid JSON).
        """
        try:
            self._validate_node(conditions)
        except (TypeError, ValueError) as e:
            raise ValidationException(f"Invalid rule conditions: {e}") from e

    def _validate_node(self, conditions: dict[str, Any]) -> None:
        """Validate one node of a condition tree, recursing into groups."""
        conditions = self._normalize_conditions(conditions)
        if conditions.get("type") in ["AND", "OR"]:
            subconditions = conditions.get("subconditions", [])
            if not subconditions:
                raise BadRequestException("Group must have subconditions")
            for sub in subconditions:
                self._validate_node(sub)
            return

        if conditions.get("type") == "CONDITION":
            field = conditions.get("field")
            operator = conditions.get("operator")
            value = conditions.get("value")

            if not field or not operator:
                raise BadRequestException("Condition missing field or operator")

            # Reject unknown fields loudly. Left unchecked, a typo'd field name
            # builds a filter that silently matches nothing.
            if (
                field not in TEXT_CONDITION_FIELDS
                and field not in NUMERIC_CONDITION_FIELDS
            ):
                raise BadRequestException(
                    f"Unknown condition field '{field}'. Valid fields: "
                    + ", ".join(
                        sorted(TEXT_CONDITION_FIELDS + NUMERIC_CONDITION_FIELDS)
                    )
                )

            if field in NUMERIC_CONDITION_FIELDS:
                if operator not in VALID_NUMERIC_OPERATORS:
                    raise BadRequestException(
                        f"Operator '{operator}' not valid for numeric field '{field}'"
                    )
                if operator == "between":
                    if not isinstance(value, list) or len(value) != 2:
                        raise BadRequestException(
                            "Value for between must be list of 2 numbers"
                        )
                    # TypeError too: a JSON null reaches float() as None and
                    # raises TypeError, which would otherwise escape validation
                    # and 500 the request instead of returning 400.
                    try:
                        float(value[0])
                        float(value[1])
                    except (TypeError, ValueError) as exc:
                        raise BadRequestException(
                            "Values for numeric field must be numbers"
                        ) from exc
                else:
                    try:
                        float(value)
                    except (TypeError, ValueError) as exc:
                        raise BadRequestException(
                            f"Value '{value}' must be a number for field '{field}'"
                        ) from exc

            if field == "service":
                # The table selector only honours ``equals`` with a known
                # service; anything else would silently match nothing.
                if operator != "equals":
                    raise BadRequestException(
                        "Field 'service' only supports the 'equals' operator"
                    )
                normalized = str(value).strip().lower().replace(" ", "_")
                if normalized not in VALID_SERVICE_VALUES:
                    raise BadRequestException(
                        f"Unknown service '{value}'. Valid services: "
                        + ", ".join(sorted(VALID_SERVICE_VALUES))
                    )
            elif field in TEXT_CONDITION_FIELDS:
                if operator not in VALID_TEXT_OPERATORS:
                    raise BadRequestException(
                        f"Operator '{operator}' not valid for text field '{field}'"
                    )
                # A blank pattern is a catch-all: ``contains ""`` matches
                # every transaction, which is never what a rule means.
                if not isinstance(value, str) or not value.strip():
                    raise BadRequestException(
                        f"Value for text field '{field}' must not be blank"
                    )

    def check_conflicts(
        self,
        conditions: dict[str, Any],
        category: str,
        tag: str,
        exclude_rule_id: int | None = None,
    ) -> None:
        """
        Reject a rule that overlaps an existing rule assigning a different pair.

        Two rules overlap when at least one current transaction matches both.
        Overlap with a rule assigning the same category/tag is harmless and
        allowed; stored rules whose conditions cannot be parsed are ignored.

        Parameters
        ----------
        conditions : dict
            Condition tree of the new (or edited) rule.
        category : str
            Category the rule assigns.
        tag : str
            Tag the rule assigns.
        exclude_rule_id : int, optional
            Rule to leave out of the comparison — the rule being edited.

        Raises
        ------
        BadRequestException
            If an overlapping rule assigns a different category/tag.
        """
        conditions = self._normalize_conditions(conditions)
        tables = self._get_tables_names_for_conditions(conditions)

        matching_tx_ids_by_table: dict[str, set[int]] = {}

        for table in tables:
            ids = self.match_repo.match_ids(table, conditions)
            if ids:
                matching_tx_ids_by_table[table] = set(ids)

        if not any(matching_tx_ids_by_table.values()):
            return

        other_rules_df = self.rules_repo.get_all_rules()
        if exclude_rule_id:
            other_rules_df = other_rules_df[other_rules_df["id"] != exclude_rule_id]

        other_rules = other_rules_df.to_dict(orient="records")

        for rule in other_rules:
            if rule["category"] == category and rule["tag"] == tag:
                continue

            rule_conds = self._stored_conditions(rule)
            if rule_conds is None:
                continue

            r_tables = self._get_tables_names_for_conditions(rule_conds)

            for table in r_tables:
                if table not in matching_tx_ids_by_table:
                    continue

                ids_to_check = list(matching_tx_ids_by_table[table])
                if not ids_to_check:
                    continue

                if self.match_repo.any_match_among(table, rule_conds, ids_to_check):
                    raise BadRequestException(
                        f"Conflict detected: This rule matches transactions that are also matched by existing rule '{rule['name']}' "
                        f"which assigns a different tag ('{rule['category']} - {rule['tag']}')."
                    )

    def _stored_conditions(self, rule: dict[str, Any]) -> dict[str, Any] | None:
        """
        Normalize a stored rule's conditions, or ``None`` if they are broken.

        Parameters
        ----------
        rule : dict
            Rule record with at least ``conditions``; ``id`` is used for the
            log line when present.

        Returns
        -------
        dict or None
            The normalized condition tree, or ``None`` when the stored value
            cannot be parsed. Broken rules are skipped everywhere (apply and
            conflict detection alike) so they never tag anything.
        """
        try:
            return self._normalize_conditions(rule["conditions"])
        except ValueError:
            # Only the row's own primary key goes into the record. The
            # rule's name is user-typed, so keeping it out removes the
            # log-injection surface (CWE-117) instead of relying on a scrub
            # a scanner cannot see through. The id is coerced to an int so
            # the logged value is provably numeric, and the absent case is
            # explicit rather than rendering a bare ``None``.
            rule_id = rule.get("id")
            logger.warning(
                "Skipping tagging rule %s: stored conditions are not valid JSON",
                int(rule_id) if rule_id is not None else "of unknown id",
            )
            return None

    def _apply_single_rule_returning_ids(
        self,
        rule: dict[str, Any],
        overwrite: bool = False,
        claimed: set[tuple[str, int]] | None = None,
        previous: tuple[str, str] | None = None,
    ) -> set[tuple[str, int]]:
        """
        Apply a single rule and return the ``(table, unique_id)`` pairs it updated.

        Parameters
        ----------
        rule : dict
            Rule dict with ``conditions``, ``category`` and ``tag`` keys.
        overwrite : bool, optional
            When ``True``, matching rows are re-tagged whatever they carry;
            otherwise only untagged rows (``category IS NULL``) are touched.
        claimed : set of (str, int), optional
            In/out. Pairs already claimed by an earlier rule in the same run
            are skipped, and every pair this rule matches is added — matched,
            not merely written, so a rule owns the rows it already agrees with
            and a later overlapping rule cannot steal them. The first matching
            rule therefore wins regardless of mode.
        previous : (str, str), optional
            The rule's former ``(category, tag)``. Rows still carrying it and
            matching the conditions are moved to the new pair even when
            ``overwrite`` is ``False`` — used when a rule is edited.

        Returns
        -------
        set of (str, int)
            Pairs actually written. Empty when the rule's conditions are
            broken, or when every matching row already says what it says.
        """
        conditions = self._stored_conditions(rule)
        if conditions is None:
            return set()
        tables = self._get_tables_names_for_conditions(conditions)

        modified_pairs: set[tuple[str, int]] = set()
        for table in tables:
            # Claim first, then narrow to the rows that need writing: a row
            # already carrying this rule's pair is still this rule's.
            matched = {
                uid
                for uid in self.match_repo.match_ids(table, conditions)
                if claimed is None or (table, uid) not in claimed
            }
            if claimed is not None:
                claimed.update((table, uid) for uid in matched)
            if not matched:
                continue

            ids_to_update = [
                uid
                for uid in self.match_repo.match_writable_ids(
                    table,
                    conditions,
                    rule["category"],
                    rule["tag"],
                    overwrite=overwrite,
                    previous=previous,
                )
                if uid in matched
            ]
            if not ids_to_update:
                continue

            self.match_repo.assign(table, ids_to_update, rule["category"], rule["tag"])

            modified_pairs.update((table, uid) for uid in ids_to_update)

        return modified_pairs

    def _get_tables_names_for_conditions(self, conditions: dict[str, Any]) -> list[str]:
        """
        Determine which tables a condition tree runs against.

        A heuristic: every ``service equals`` condition anywhere in the tree
        is collected regardless of its ``AND``/``OR`` position, and the rule
        runs against the union of the named services' tables.

        Parameters
        ----------
        conditions : dict
            Normalized condition tree.

        Returns
        -------
        list[str]
            Table names; both transaction tables when no service is named.
        """
        services_found: set[str] = set()
        self._collect_services(conditions, services_found)

        if not services_found:
            return [Tables.CREDIT_CARD.value, Tables.BANK.value]

        tables = []

        if "credit_card" in services_found:
            tables.append(Tables.CREDIT_CARD.value)
        if "bank" in services_found:
            tables.append(Tables.BANK.value)

        return tables

    def _collect_services(self, node: dict[str, Any], services: set[str]) -> None:
        """
        Recursively collect ``service`` field values from a condition tree.

        Parameters
        ----------
        node : dict
            Condition tree node.
        services : set[str]
            Mutable set that is updated in-place with any service values found.
        """
        if node.get("type") in ["AND", "OR"]:
            for sub in node.get("subconditions", []):
                self._collect_services(sub, services)
        elif (
            node.get("type") == "CONDITION"
            and node.get("field") == "service"
            and node.get("operator") == "equals"
        ):
            services.add(str(node.get("value")).lower().replace(" ", "_"))

    def auto_tag_credit_cards_bills(self) -> int:
        """
        Auto-tag bank debit transactions as credit card bill payments.

        For each untagged bank transaction, checks whether its amount matches the
        total credit card charges for any known CC account in the same calendar month
        (CC dates are shifted +1 month +1 day to align billing cycles). Matching is
        done within a ±0.01 tolerance. Exactly one matching bank transaction per
        CC account per month is tagged with ``"Credit Cards"`` category and the
        corresponding CC tag.

        Returns
        -------
        int
            Number of bank transactions that were tagged as credit card bill payments.

        Notes
        -----
        A TODO in the implementation notes frequent mismatches between the CC monthly
        total and the bank debit amount; this function may under-tag in practice.
        """
        # TODO: figure out why we have so many mismatches between credit card monthly amount and bank cc bill
        bank_data = self.transactions_repo.get_table(service=Tables.BANK.value)
        bank_data = bank_data[bank_data["category"].isna()].copy()
        bank_data["date"] = pd.to_datetime(bank_data["date"])
        bank_data["month"] = bank_data["date"].dt.strftime("%Y-%m")

        if bank_data.empty:
            return 0

        cc_data = self.transactions_repo.get_table(service=Tables.CREDIT_CARD.value)
        # A card is billed the following month, and its scraped dates run one
        # day early, so shift by a month and a day to land on the bill's month.
        cc_data["date"] = pd.to_datetime(cc_data["date"]) + pd.DateOffset(
            months=1, days=1
        )
        cc_data["month"] = cc_data["date"].dt.strftime("%Y-%m")

        if cc_data.empty:
            return 0

        count = 0
        cc_tags = self.categories_tags_service.categories_and_tags.get(
            "Credit Cards", []
        )
        # Tags are title-cased on creation ("Isracard - Main Card - 1234")
        # while the scraped rows keep the provider's own casing ("isracard"),
        # so provider and account name must be compared case-insensitively.
        cc_data["_provider_key"] = (
            cc_data[TransactionsTableFields.PROVIDER.value].astype("string").str.lower()
        )
        cc_data["_account_key"] = (
            cc_data[TransactionsTableFields.ACCOUNT_NAME.value]
            .astype("string")
            .str.lower()
        )
        for bank_month, bank_month_data in bank_data.sort_values("month").groupby(
            "month"
        ):
            cc_month_data = cc_data[cc_data["month"] == bank_month]
            for cc_tag in cc_tags:
                parts = cc_tag.rsplit(" - ", 2)
                if len(parts) != 3:
                    continue
                provider, account_name, account_number = parts
                cc_tag_month_data_amount = cc_month_data[
                    (cc_month_data["_provider_key"] == provider.lower())
                    & (cc_month_data["_account_key"] == account_name.lower())
                    & (
                        cc_month_data[TransactionsTableFields.ACCOUNT_NUMBER.value]
                        .astype("string")
                        .str.endswith(account_number, na=False)
                    )
                ][TransactionsTableFields.AMOUNT.value].sum()

                # A bank debit of exactly the card's monthly total is its bill.
                bank_tag_month_data_amount = bank_month_data[
                    (
                        bank_month_data[TransactionsTableFields.AMOUNT.value]
                        >= cc_tag_month_data_amount - 0.01
                    )
                    & (
                        bank_month_data[TransactionsTableFields.AMOUNT.value]
                        <= cc_tag_month_data_amount + 0.01
                    )
                ]
                if len(bank_tag_month_data_amount) == 1:
                    unique_id = bank_tag_month_data_amount.iloc[0][
                        TransactionsTableFields.UNIQUE_ID.value
                    ]
                    # A bill row becomes "Credit Cards", never an investment,
                    # so it skips the per-row investment realignment that
                    # update_tagging_by_id runs.
                    self.transactions_repo.get_repo_by_source(
                        Tables.BANK.value
                    ).update_tagging_by_unique_id(unique_id, "Credit Cards", cc_tag)
                    count += 1

        return count
