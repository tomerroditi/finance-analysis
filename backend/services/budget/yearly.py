"""Yearly budget service — per-year category/tag envelopes."""

import pandas as pd

from backend.constants.budget import (
    ALL_TAGS,
    AMOUNT,
    CATEGORY,
    ID,
    IS_CLOSED,
    MONTH,
    NAME,
    PERIOD_MONTHLY,
    PERIOD_TYPE,
    PERIOD_YEARLY,
    TAGS,
    YEAR,
)
from backend.constants.tables import TransactionsTableFields
from backend.errors import EntityNotFoundException, ValidationException
from backend.services.budget.core import BudgetService, _auto_fill_lock, _today
from backend.services.pending_refunds_service import restore_gross_amounts


class YearlyBudgetService(BudgetService):
    """Service for managing yearly budget rules.

    A yearly budget is a flat list of independent ``(category, tags)`` rules for
    a calendar year. Spend accumulates over the whole year. There is no overall
    cap and no synthetic "Other Expenses" entry. Yearly rules are mutually
    exclusive with monthly rules on ``(category, tag)`` within the same year.

    A rule can be *closed* once the year's commitment behind it is settled —
    the annual insurance is paid, the trip is over. Closing is not a delete
    and not an edit: the rule keeps its amount, its spend and its place in this
    year's tab, and it still claims its ``(category, tag)`` against monthly
    rules. What it loses is the budget Overview, where it is no longer an
    envelope the running month is measured against, and the attention it drew
    there — see :meth:`set_rule_closed`.
    """

    def get_all_rules(self) -> pd.DataFrame:
        """Get all yearly budget rules (period_type == 'yearly'), MONTH dropped."""
        rules = super().get_all_rules()
        if rules.empty:
            return rules
        return rules.loc[rules[PERIOD_TYPE] == PERIOD_YEARLY].drop(columns=[MONTH])

    def get_year_rules(self, year: int) -> pd.DataFrame:
        """Yearly rules scoped to a single calendar year."""
        rules = self.get_all_rules()
        if rules.empty:
            return rules
        return rules.loc[rules[YEAR] == year]

    @staticmethod
    def _rule_is_closed(rule: pd.Series) -> bool:
        """Whether one yearly rule row carries the closed flag.

        Parameters
        ----------
        rule : pd.Series
            One row of a ``get_all_rules``-style frame.

        Returns
        -------
        bool
            ``True`` only for a row explicitly flagged closed. Rows written
            before the flag existed hold ``NULL``, which pandas reads back as
            ``NaN`` — neither of those is closed.
        """
        if IS_CLOSED not in rule:
            return False
        value = rule[IS_CLOSED]
        if value is None or pd.isna(value):
            return False
        return int(value) == 1

    def set_rule_closed(self, id_: int, closed: bool) -> None:
        """Close a settled yearly envelope, or reopen a closed one.

        Closing is deliberately neither a delete nor a zeroing: the rule keeps
        its allocation, its spend and its row in the year's tab, and it goes on
        claiming its ``(category, tag)`` against monthly rules for the year — a
        closed envelope's spend must not suddenly reappear inside the monthly
        budget. All it loses is the budget Overview, where a settled commitment
        is no longer something the running month can be measured against.

        Parameters
        ----------
        id_ : int
            Yearly rule id.
        closed : bool
            ``True`` closes the rule, ``False`` reopens it.

        Raises
        ------
        EntityNotFoundException
            If ``id_`` is not a yearly rule.
        """
        self._yearly_row(id_)
        self.budget_repository.set_closed_by_id(id_, closed, PERIOD_YEARLY)

    def is_rule_closed(self, id_: int) -> bool:
        """Whether the yearly rule ``id_`` has been closed.

        Raises
        ------
        EntityNotFoundException
            If ``id_`` is not a yearly rule.
        """
        return self._rule_is_closed(self._yearly_row(id_))

    def _validate(
        self,
        name: str,
        category: str,
        tags: list[str],
        amount: float,
        year: int,
        id_: int | None,
    ) -> None:
        """Validate a yearly rule; raise ``ValueError`` on failure.

        Checks: non-blank name/category, well-formed tags, positive amount,
        name uniqueness within the year, and mutual exclusion against monthly
        rules for the year.
        """
        if not name or not str(name).strip():
            raise ValueError("Please enter a name")
        if not category:
            raise ValueError("Please select a category")
        tags_error = self._tags_error(tags)
        if tags_error is not None:
            raise ValueError(tags_error)
        if amount <= 0:
            raise ValueError("Amount must be a positive number")

        existing = self.get_year_rules(year)
        if not existing.empty:
            dupes = existing.loc[existing[NAME] == name]
            if id_ is not None:
                dupes = dupes.loc[dupes[ID] != id_]
            if not dupes.empty:
                raise ValueError(
                    f"A yearly rule with the name '{name}' already exists for {year}."
                )

        conflicts = self.find_conflicting_tags(
            category, tags, year, PERIOD_MONTHLY, exclude_rule_id=id_
        )
        if conflicts:
            joined = ", ".join(conflicts)
            raise ValueError(
                f"{joined} is already used by your monthly budget for {year}. "
                f"A tag can't be in both for the same year."
            )

        # A (category, tag) may not be covered by two yearly rules in the same
        # year. Unlike monthly rules (bounded by the Total Budget cap), yearly
        # rules have no overall cap, so a shared tag would double-count in the
        # roll-up's total_spent/remaining/health.
        yearly_conflicts = self.find_conflicting_tags(
            category, tags, year, PERIOD_YEARLY, exclude_rule_id=id_
        )
        if yearly_conflicts:
            if yearly_conflicts == [ALL_TAGS]:
                raise ValueError(
                    f"Another yearly rule already covers the '{category}' "
                    f"category for {year}."
                )
            joined = ", ".join(yearly_conflicts)
            raise ValueError(
                f"{joined} is already used by another yearly rule for {year}. "
                f"A tag can't be in two yearly rules for the same year."
            )

        if self.is_category_project_owned(category):
            raise ValueError(
                f"The '{category}' category belongs to a project budget. "
                f"A yearly rule can't target a project category."
            )

    def create_rule(
        self,
        name: str,
        amount: float,
        category: str,
        tags: str | list[str],
        year: int,
    ) -> None:
        """Create a yearly rule after validation. Raises ``ValueError`` if invalid."""
        name = str(name).strip()
        parsed_tags = self._parse_tags(tags)
        self._validate(name, category, parsed_tags, amount, year, None)
        self.add_rule(
            name,
            amount,
            category,
            parsed_tags,
            month=None,
            year=year,
            period_type=PERIOD_YEARLY,
        )

    def _yearly_row(self, id_: int) -> pd.Series:
        """Return the yearly rule with ``id_``.

        Raises
        ------
        EntityNotFoundException
            If no rule has that id, or the rule is monthly/project — the
            yearly endpoints must never reach across into another kind.
        """
        current = self.get_all_rules()
        row = current.loc[current[ID] == id_] if not current.empty else current
        if row.empty:
            raise EntityNotFoundException(f"No yearly rule found with ID {id_}.")
        return row.iloc[0]

    def update_rule(self, id_: int, **fields):
        """Update a yearly rule with validation of any category/tags/name/amount change.

        Allowed fields: ``name``, ``amount``, ``category``, ``tags``. The rule's
        ``year`` is immutable via this method.

        Raises
        ------
        EntityNotFoundException
            If ``id_`` is not a yearly rule.
        """
        valid_fields = {NAME, AMOUNT, CATEGORY, TAGS}
        if not all(k in valid_fields for k in fields):
            raise ValidationException(
                f"Invalid fields for update. Valid fields: {valid_fields}"
            )
        row = self._yearly_row(id_)
        year = int(row[YEAR])
        if NAME in fields:
            fields[NAME] = str(fields[NAME]).strip()
        name = fields.get(NAME, row[NAME])
        amount = fields.get(AMOUNT, row[AMOUNT])
        category = fields.get(CATEGORY, row[CATEGORY])
        parsed_tags = self._parse_tags(fields.get(TAGS, row[TAGS]))
        self._validate(name, category, parsed_tags, amount, year, id_)

        if TAGS in fields and isinstance(fields[TAGS], list):
            fields[TAGS] = ";".join(fields[TAGS])
        self.budget_repository.update(id_, **fields)

    def delete_rule(self, id_: int) -> None:
        """Delete a yearly rule; a monthly/project id is not found here."""
        self._yearly_row(id_)
        super().delete_rule(id_)

    def get_yearly_budget_view(
        self, year: int, include_split_parents: bool = False
    ) -> list[dict] | None:
        """Compute spend-vs-limit per yearly rule for a calendar year.

        Returns ``None`` when the year has no yearly rules. Otherwise a flat list
        of ``{rule, current_amount, data, allow_edit, allow_delete, closed}`` —
        no total rule, no "Other Expenses" remainder. Closed rules are listed
        like any other: this is the envelope's own tab, where its history
        belongs; it is the Overview that drops them.
        """
        rules = self.get_year_rules(year)
        if rules.empty:
            return None

        expenses = self.get_filtered_expenses(
            exclude_pending_refunds=True,
            include_split_parents=include_split_parents,
            # Envelopes report what a month cost, net of refunds matched to
            # their purchase — the same definition the dashboard now uses.
            net_refunds=True,
        )
        if not expenses.empty:
            year_data = expenses.loc[
                pd.to_datetime(expenses[TransactionsTableFields.DATE.value]).dt.year
                == year
            ]
        else:
            year_data = expenses

        view = []
        for _, rule in rules.iterrows():
            tags = rule[TAGS]
            if year_data.empty:
                cat_data = year_data
            else:
                cat_data = year_data[
                    year_data[TransactionsTableFields.CATEGORY.value] == rule[CATEGORY]
                ]
                if not self._is_all_tags(tags):
                    cat_data = cat_data[
                        cat_data[TransactionsTableFields.TAG.value].isin(tags)
                    ]
            amt = (
                cat_data[TransactionsTableFields.AMOUNT.value].sum() * -1
                if not cat_data.empty
                else 0.0
            )
            view.append(
                {
                    "rule": rule.to_dict(),
                    "current_amount": amt,
                    "data": restore_gross_amounts(cat_data).to_dict(orient="records"),
                    "allow_edit": True,
                    "allow_delete": True,
                    "closed": self._rule_is_closed(rule),
                }
            )
        return view

    def get_year_summary(self, year: int) -> dict:
        """Computed, display-only roll-up for the year header.

        The money figures cover every rule, closed ones included — an envelope
        that has been settled still allocated and still spent this year, and
        dropping it would make the year's own totals disagree with the rows
        listed under them. The health counts are the opposite: they are a call
        to act, and a closed envelope is one the user has said is finished, so
        it is counted apart in ``closed`` and can never be the year's
        ``biggest_overspend``.

        Returns
        -------
        dict
            ``total_allocated``, ``total_spent``, ``remaining``, ``on_track``
            (count of open rules at/under budget), ``over`` (count of open
            rules over budget), ``closed`` (count of closed rules), and
            ``biggest_overspend`` (``{"name", "percentage"}`` or ``None``).
        """
        view = self.get_yearly_budget_view(year) or []
        total_allocated = sum(float(e["rule"].get(AMOUNT) or 0) for e in view)
        total_spent = sum(float(e["current_amount"] or 0) for e in view)
        on_track = 0
        over = 0
        closed = 0
        biggest = None
        for e in view:
            if e.get("closed"):
                closed += 1
                continue
            amount = float(e["rule"].get(AMOUNT) or 0)
            spent = float(e["current_amount"] or 0)
            pct = spent / amount if amount > 0 else 0.0
            if amount > 0 and spent > amount:
                over += 1
                if biggest is None or pct > biggest["percentage"]:
                    biggest = {
                        "name": str(e["rule"].get(NAME) or ""),
                        "percentage": pct,
                    }
            else:
                on_track += 1
        return {
            "total_allocated": total_allocated,
            "total_spent": total_spent,
            "remaining": total_allocated - total_spent,
            "on_track": on_track,
            "over": over,
            "closed": closed,
            "biggest_overspend": biggest,
        }

    def get_alerts(self, year: int, warning_threshold: float = 0.8) -> list[dict]:
        """Yearly rules whose spend reached the warning threshold.

        Mirrors ``MonthlyBudgetService.get_alerts`` — ``percentage = spent/amount``;
        ``critical`` at ≥ 1.0, ``warning`` in ``[threshold, 1.0)``. There is no
        Total Budget / Other Expenses row to skip. Closed rules are skipped: an
        alert asks the user to do something about an envelope they are still
        spending from, and a settled one is exactly what closing says it isn't.
        """
        view = self.get_yearly_budget_view(year)
        if view is None:
            return []
        alerts = []
        for entry in view:
            if entry.get("closed"):
                continue
            rule = entry["rule"]
            amount = float(rule.get(AMOUNT) or 0)
            if amount <= 0:
                continue
            spent = float(entry.get("current_amount") or 0)
            percentage = spent / amount
            if percentage < warning_threshold:
                continue
            alerts.append(
                {
                    "rule_id": int(rule[ID]),
                    "name": str(rule.get(NAME) or ""),
                    "category": str(rule.get(CATEGORY) or ""),
                    "tags": list(rule.get(TAGS) or []),
                    "amount": amount,
                    "spent": spent,
                    "percentage": percentage,
                    "severity": "critical" if percentage >= 1.0 else "warning",
                }
            )
        alerts.sort(key=lambda a: a["percentage"], reverse=True)
        return alerts

    def auto_carry_forward(self, year: int) -> dict | None:
        """Copy the latest prior year's yearly rules into an empty ``year``.

        Only runs for the current or a future year (never rewrites history) and
        only when ``year`` has no yearly rules yet. Tags that conflict with
        monthly rules for ``year`` are stripped; a rule left with no tags is
        skipped entirely.

        Returns
        -------
        dict or None
            ``{"copied_from": <int year>, "skipped": [<tag>, ...]}`` when rules
            were copied, else ``None``.
        """
        if year < _today().year:
            return None
        with _auto_fill_lock:
            self.db.rollback()
            if not self.get_year_rules(year).empty:
                return None
            all_rules = self.get_all_rules()
            if all_rules.empty:
                return None
            prior = all_rules.loc[all_rules[YEAR] < year]
            if prior.empty:
                return None
            source_year = int(prior[YEAR].max())
            source_rules = all_rules.loc[all_rules[YEAR] == source_year]

            skipped = self._copy_rules(
                source_rules,
                conflict_period_type=PERIOD_MONTHLY,
                target_year=year,
                period_type=PERIOD_YEARLY,
            )
            return {"copied_from": source_year, "skipped": skipped}

    def force_copy_from_prior_year(self, year: int) -> dict | None:
        """Force-copy the latest prior year's yearly rules into ``year``.

        This is the explicit user-triggered "Copy from previous year" action
        (the ``/yearly/{year}/copy`` route), distinct from
        ``auto_carry_forward``: it does not gate on ``year`` being the
        current/future year, and it does not require ``year`` to already be
        empty — the user may be intentionally overwriting an existing year.

        To avoid data loss, the source year is resolved *first*. Only once a
        valid prior year with yearly rules is confirmed does this delete
        ``year``'s existing rules and copy the source rules forward. If no
        prior year has any yearly rules, nothing is deleted.

        Returns
        -------
        dict or None
            ``{"copied_from": <int year>, "skipped": [<tag>, ...]}`` when
            rules were copied. ``None`` when there is no prior year with
            yearly rules to copy from — in that case ``year``'s existing
            rules (if any) are left untouched.
        """
        all_rules = self.get_all_rules()
        if all_rules.empty:
            return None
        prior = all_rules.loc[all_rules[YEAR] < year]
        if prior.empty:
            return None
        source_year = int(prior[YEAR].max())
        source_rules = all_rules.loc[all_rules[YEAR] == source_year]

        with _auto_fill_lock:
            self.db.rollback()
            existing = self.get_year_rules(year)
            for _, r in existing.iterrows():
                self.delete_rule(int(r[ID]))

            skipped = self._copy_rules(
                source_rules,
                conflict_period_type=PERIOD_MONTHLY,
                target_year=year,
                period_type=PERIOD_YEARLY,
            )
            return {"copied_from": source_year, "skipped": sorted(set(skipped))}

    def get_yearly_analysis(
        self, year: int, include_split_parents: bool = False
    ) -> dict:
        """Bundle the yearly view, computed roll-up, alerts, and carry-forward report."""
        carried_from = None
        skipped_conflicts: list[str] = []
        if self.get_year_rules(year).empty and year >= _today().year:
            result = self.auto_carry_forward(year)
            if result is not None:
                carried_from = result["copied_from"]
                skipped_conflicts = result["skipped"]

        view = self.get_yearly_budget_view(year, include_split_parents)
        return {
            "rules": view or [],
            "summary": self.get_year_summary(year),
            "alerts": self.get_alerts(year),
            "carried_from": carried_from,
            "skipped_conflicts": sorted(set(skipped_conflicts)),
        }
