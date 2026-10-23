"""
Budget rule store — the one write path for budget rules.

A budget rule is one of three kinds, recorded in ``budget_rules.period_type``:
a monthly rule (one month's cap on a category/tags, under that month's
``Total Budget``), a yearly rule (a per-year envelope), or a project rule (a
project's ``all_tags`` total, or one of its tag rules). Every create, edit and
delete goes through :class:`BudgetRuleStore`, which validates the write by
the rule's kind — the caller names the kind on create, an edit reads it off
the stored row — so no endpoint can reach a kind's rows without that kind's
checks, and no row is ever written with its kind left to be guessed from
which of ``year``/``month`` are null.

The cross-kind invariants are checked here too, from one read of the table:

- a (category, tag) is claimed by monthly rules or by a yearly rule within a
  year, never both;
- a category that belongs to a project is never used by a monthly or yearly
  rule, and the other way round.

The checks themselves are pure functions over the rules frame, so a caller
that already holds the rules can validate without another read.
"""

from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.budget import (
    ALL_TAGS,
    AMOUNT,
    CATEGORY,
    ID,
    MONTH,
    NAME,
    PERIOD_MONTHLY,
    PERIOD_PROJECT,
    PERIOD_TYPE,
    PERIOD_YEARLY,
    TAGS,
    TOTAL_BUDGET,
    YEAR,
)
from backend.errors import EntityNotFoundException, ValidationException
from backend.repositories.budget_repository import BudgetRepository
from backend.services.budget.ledger import is_all_tags

KINDS = (PERIOD_MONTHLY, PERIOD_YEARLY, PERIOD_PROJECT)
EDITABLE_FIELDS = {NAME, AMOUNT, CATEGORY, TAGS}


def parse_tags(tags: str | list[str] | None) -> list[str]:
    """Normalise a tags value (``"a;b"`` or ``["a", "b"]``) into a list."""
    if tags is None:
        return []
    if isinstance(tags, str):
        return tags.split(";")
    return list(tags)


def tags_error(tags: list[str] | None) -> str | None:
    """Return a validation message for a malformed tag list, else ``None``.

    Tags are stored as a ``;``-joined string, so a tag containing ``;`` would
    silently split into two on the next read; blank tags match nothing and
    only clutter the rule.
    """
    if not tags:
        return "Please select at least one tag"
    for tag in tags:
        if not isinstance(tag, str) or not tag.strip():
            return "Tags can't be empty"
        if ";" in tag:
            return "Tags can't contain ';'"
    return None


def conflicting_tags(
    rules: pd.DataFrame,
    category: str,
    tags: list[str],
    year: int,
    other_kind: str,
    *,
    exclude_rule_id: int | None = None,
) -> list[str]:
    """Return incoming tags that collide with existing ``other_kind`` rules.

    Two rules conflict when they share ``category`` and ``year`` and at least
    one tag. An ``all_tags`` sentinel on either side claims the whole category,
    so every incoming (non-sentinel) tag conflicts.

    Parameters
    ----------
    rules : pd.DataFrame
        All budget rules, tags as lists.
    category : str
        Category of the incoming rule.
    tags : list[str]
        Incoming tag list (may be the ``all_tags`` sentinel).
    year : int
        Calendar year the incoming rule applies to.
    other_kind : str
        The budget kind to check against (``"yearly"`` when validating a
        monthly rule, ``"monthly"`` when validating a yearly one).
    exclude_rule_id : int, optional
        A rule id to ignore (the rule being edited).

    Returns
    -------
    list[str]
        Sorted conflicting tag names. Empty when there is no conflict. When the
        incoming rule is itself ``all_tags`` and any other rule exists in the
        category+year, returns ``["all_tags"]`` to signal a whole-category
        conflict.
    """
    if rules.empty:
        return []
    others = rules.loc[
        (rules[PERIOD_TYPE] == other_kind)
        & (rules[YEAR] == year)
        & (rules[CATEGORY] == category)
    ]
    if exclude_rule_id is not None:
        others = others.loc[others[ID] != exclude_rule_id]
    if others.empty:
        return []

    if is_all_tags(tags):
        return [ALL_TAGS]

    conflicts: set[str] = set()
    for other_tags in others[TAGS]:
        if is_all_tags(other_tags):
            conflicts.update(tags)
        else:
            conflicts.update(set(tags) & set(other_tags))
    return sorted(conflicts)


def project_categories(rules: pd.DataFrame) -> set[str]:
    """Return the categories owned by a project."""
    if rules.empty:
        return set()
    return set(rules.loc[rules[PERIOD_TYPE] == PERIOD_PROJECT, CATEGORY].dropna())


def budgeted_categories(rules: pd.DataFrame) -> set[str]:
    """Return the categories a monthly or yearly rule uses.

    The ``Total Budget`` cap is not a real category and is never counted.
    """
    if rules.empty:
        return set()
    used = rules.loc[rules[PERIOD_TYPE].isin([PERIOD_MONTHLY, PERIOD_YEARLY]), CATEGORY]
    return set(used.dropna()) - {TOTAL_BUDGET}


def rule_error(
    rules: pd.DataFrame,
    kind: str,
    name: str,
    category: str,
    tags: list[str],
    amount: float,
    year: int | None = None,
    month: int | None = None,
    id_: int | None = None,
) -> str | None:
    """Return why a rule of ``kind`` can't be written, or ``None`` if it can.

    Checks what every rule needs (a name, a category, well-formed tags, an
    amount), then the kind's own rules:

    - **monthly** — a name unique in its month; one ``Total Budget`` per
      month, never below the sum of the month's other rules; any other rule
      needs that total and must fit under it, may not claim a tag a yearly
      rule of the same year claims, and an ``all_tags`` rule may not join
      specific-tag rules of its category;
    - **yearly** — a name unique in its year, and no tag shared with a monthly
      rule or another yearly rule of that year;
    - **project** — a name unique in the project; one ``all_tags`` total per
      project, never below the sum of its tag rules; a tag rule needs that
      total, must fit under it, and may be zero (a project lists every tag of
      its category, budgeted or not).

    A monthly or yearly rule may not move onto a project's category, nor a
    project rule onto a category a monthly or yearly rule uses. Those two are
    checked only when the rule takes the category on — on create, or when an
    edit changes it — so a rule written before the exclusion existed can
    still be edited in place; such overlaps are reported by
    :meth:`BudgetRuleStore.find_category_overlaps` instead.

    Parameters
    ----------
    rules : pd.DataFrame
        All budget rules, tags as lists.
    kind : str
        ``"monthly"``, ``"yearly"`` or ``"project"``.
    name, category, tags, amount
        The rule as it would be written.
    year, month : int or None
        The rule's period: both for monthly, ``year`` for yearly, neither for
        project.
    id_ : int or None
        The rule being edited; ``None`` on create.

    Returns
    -------
    str or None
        The first failed check's message, or ``None``.
    """
    if kind not in KINDS:
        return f"Unknown budget kind '{kind}'"
    name = "" if name is None else str(name).strip()
    if not name:
        return "Please enter a name"
    if not category:
        return "Please select a category"
    error = tags_error(tags)
    if error is not None:
        return error

    others = rules if id_ is None or rules.empty else rules.loc[rules[ID] != id_]
    stored_category = None
    if id_ is not None and not rules.empty:
        stored = rules.loc[rules[ID] == id_, CATEGORY]
        stored_category = stored.iloc[0] if not stored.empty else None
    takes_category = category != stored_category

    if kind == PERIOD_PROJECT:
        return _project_error(others, name, category, tags, amount, takes_category)
    if amount <= 0:
        return "Amount must be a positive number"
    if kind == PERIOD_YEARLY:
        return _yearly_error(rules, others, name, category, tags, year, id_)
    return _monthly_error(
        rules, others, name, category, tags, amount, year, month, id_, takes_category
    )


def _monthly_error(
    rules: pd.DataFrame,
    others: pd.DataFrame,
    name: str,
    category: str,
    tags: list[str],
    amount: float,
    year: int | None,
    month: int | None,
    id_: int | None,
    takes_category: bool,
) -> str | None:
    """Return the first monthly-rule check ``rule_error`` documents that fails."""
    if year is None or month is None:
        return "A monthly rule needs a year and a month"
    month_rules = (
        others
        if others.empty
        else others.loc[
            (others[PERIOD_TYPE] == PERIOD_MONTHLY)
            & (others[YEAR] == year)
            & (others[MONTH] == month)
        ]
    )
    if not month_rules.empty and (month_rules[NAME] == name).any():
        return f"A rule with the name '{name}' already exists for this month."

    is_total = (
        month_rules[CATEGORY] == TOTAL_BUDGET
        if not month_rules.empty
        else pd.Series(dtype=bool)
    )
    other_rules_amount = month_rules.loc[~is_total, AMOUNT].sum()
    totals = month_rules.loc[is_total, AMOUNT]

    if category == TOTAL_BUDGET:
        if not totals.empty:
            return "This month already has a Total Budget rule"
        if amount < other_rules_amount:
            return "The total budget must be greater than the sum of all other rules"
        return None

    if takes_category and category in project_categories(rules):
        return (
            f"The '{category}' category belongs to a project budget. "
            f"A monthly rule can't target a project category."
        )
    conflicts = conflicting_tags(
        rules, category, tags, year, PERIOD_YEARLY, exclude_rule_id=id_
    )
    if conflicts:
        return (
            f"{', '.join(conflicts)} is already used by your yearly budget for "
            f"{year}. A tag can't be in both for the same year."
        )
    if totals.empty:
        return "Create a Total Budget rule for this month before adding category rules"
    if other_rules_amount + amount > totals.iloc[0]:
        return "The total budget is exceeded"

    # An all_tags rule cannot join existing specific-tag rules in the same
    # category: it would budget the whole category on top of rules that
    # already budget parts of it.
    #
    # The reverse is deliberately allowed. A specific-tag rule under an
    # existing all_tags rule is how a sub-budget inside a broader category
    # is expressed, and the shipped demo data is shaped that way (Food
    # carries an all_tags rule alongside Groceries and Restaurants).
    if is_all_tags(tags) and (month_rules[CATEGORY] == category).any():
        return f"Cannot have {ALL_TAGS} for a category with existing specific tag rules"
    return None


def _yearly_error(
    rules: pd.DataFrame,
    others: pd.DataFrame,
    name: str,
    category: str,
    tags: list[str],
    year: int | None,
    id_: int | None,
) -> str | None:
    """Return the first yearly-rule check ``rule_error`` documents that fails."""
    if year is None:
        return "A yearly rule needs a year"
    if (
        not others.empty
        and (
            (others[PERIOD_TYPE] == PERIOD_YEARLY)
            & (others[YEAR] == year)
            & (others[NAME] == name)
        ).any()
    ):
        return f"A yearly rule with the name '{name}' already exists for {year}."

    conflicts = conflicting_tags(
        rules, category, tags, year, PERIOD_MONTHLY, exclude_rule_id=id_
    )
    if conflicts:
        return (
            f"{', '.join(conflicts)} is already used by your monthly budget for "
            f"{year}. A tag can't be in both for the same year."
        )

    # Unlike monthly rules (bounded by the Total Budget cap), yearly rules
    # have no overall cap, so a tag shared by two of them would double-count
    # in the year's total_spent/remaining/health.
    conflicts = conflicting_tags(
        rules, category, tags, year, PERIOD_YEARLY, exclude_rule_id=id_
    )
    if conflicts == [ALL_TAGS]:
        return (
            f"Another yearly rule already covers the '{category}' category for {year}."
        )
    if conflicts:
        return (
            f"{', '.join(conflicts)} is already used by another yearly rule for "
            f"{year}. A tag can't be in two yearly rules for the same year."
        )

    if category in project_categories(rules):
        return (
            f"The '{category}' category belongs to a project budget. "
            f"A yearly rule can't target a project category."
        )
    return None


def _project_error(
    others: pd.DataFrame,
    name: str,
    category: str,
    tags: list[str],
    amount: float,
    takes_category: bool,
) -> str | None:
    """Return the first project-rule check ``rule_error`` documents that fails."""
    anchor = is_all_tags(tags)
    if anchor and amount <= 0:
        return "Amount must be a positive number"
    if amount < 0:
        return "Amount can't be negative"
    if takes_category and category in budgeted_categories(others):
        return (
            f"The '{category}' category is already used by a monthly or yearly "
            f"budget. A category can't be in both a project and a monthly/yearly "
            f"budget."
        )

    project = (
        others
        if others.empty
        else others.loc[
            (others[PERIOD_TYPE] == PERIOD_PROJECT) & (others[CATEGORY] == category)
        ]
    )
    if not project.empty and (project[NAME] == name).any():
        return f"A project rule with the name '{name}' already exists."

    is_anchor = (
        project[TAGS].apply(is_all_tags) if not project.empty else pd.Series(dtype=bool)
    )
    tag_rules_amount = project.loc[~is_anchor, AMOUNT].sum()
    totals = project.loc[is_anchor, AMOUNT]
    if anchor:
        if not totals.empty:
            return "This project already has a total budget rule"
        if amount < tag_rules_amount:
            return "The total budget must be greater than the sum of all other rules"
        return None
    if totals.empty:
        return "Create the project's total budget rule before adding tag rules"
    if tag_rules_amount + amount > totals.iloc[0]:
        return "The total budget is exceeded"
    return None


class BudgetRuleStore:
    """Create, edit and delete budget rules, each write checked by its kind."""

    def __init__(self, db: Session) -> None:
        """
        Initialize the store.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.repository = BudgetRepository(db)

    def all(self) -> pd.DataFrame:
        """
        Return every budget rule, tags parsed into lists.

        Returns
        -------
        pd.DataFrame
            All rules. The ``tags`` column is a list of strings instead of the
            raw semicolon-separated string stored in the DB.
        """
        rules = self.repository.read_all()
        if not rules.empty:
            rules[TAGS] = rules[TAGS].apply(
                lambda x: x.split(";") if isinstance(x, str) else []
            )
        return rules

    def of_kind(self, kind: str) -> pd.DataFrame:
        """Return the rules of one kind, tags parsed into lists."""
        rules = self.all()
        if rules.empty:
            return rules
        return rules.loc[rules[PERIOD_TYPE] == kind]

    def get(
        self, rule_id: int, kind: str | None = None, rules: pd.DataFrame | None = None
    ) -> pd.Series:
        """
        Return one rule.

        Parameters
        ----------
        rule_id : int
            Rule id.
        kind : str, optional
            When given, a rule of any other kind is treated as missing — an
            endpoint scoped to one kind must never reach into another.
        rules : pd.DataFrame, optional
            An already-read :meth:`all` frame to look the rule up in.

        Raises
        ------
        EntityNotFoundException
            If no rule (of ``kind``) has that id.
        """
        if rules is None:
            rules = self.all()
        row = rules.loc[rules[ID] == rule_id] if not rules.empty else rules
        if not row.empty and kind is not None:
            row = row.loc[row[PERIOD_TYPE] == kind]
        if row.empty:
            label = f"{kind} rule" if kind else "rule"
            raise EntityNotFoundException(f"No {label} found with ID {rule_id}.")
        return row.iloc[0]

    def insert(
        self,
        name: str,
        amount: float,
        category: str,
        tags: str | list[str],
        month: int | None = None,
        year: int | None = None,
        *,
        kind: str,
    ) -> None:
        """
        Write a rule without validating it.

        For the system's own writes whose source was already valid — a month
        or year copied forward, the zero-budget rule a project mints for a
        tag it has not seen — never for user input, which goes through
        :meth:`create`.

        Parameters
        ----------
        name, amount, category
            The rule.
        tags : str or list[str]
            Tags the rule covers. Lists are joined with ``;``.
        month, year : int, optional
            The rule's period (see :func:`rule_error`).
        kind : str
            ``"monthly"``, ``"yearly"`` or ``"project"``.
        """
        if kind not in KINDS:
            raise ValidationException(f"Unknown budget kind '{kind}'")
        tags_str = ";".join(tags) if isinstance(tags, list) else tags
        self.repository.add(
            name, amount, category, tags_str, month, year, period_type=kind
        )

    def create(
        self,
        kind: str,
        name: str,
        amount: float,
        category: str,
        tags: str | list[str],
        year: int | None = None,
        month: int | None = None,
    ) -> None:
        """
        Validate and write a new rule of ``kind``.

        Raises
        ------
        ValidationException
            If the rule fails :func:`rule_error`.
        """
        name = str(name).strip()
        parsed = parse_tags(tags)
        if kind == PERIOD_PROJECT:
            year = month = None
        elif kind == PERIOD_YEARLY:
            month = None
        error = rule_error(
            self.all(), kind, name, category, parsed, amount, year, month
        )
        if error is not None:
            raise ValidationException(error)
        self.insert(name, amount, category, parsed, month, year, kind=kind)

    def update(self, rule_id: int, kind: str | None = None, **fields: Any) -> None:
        """
        Validate and apply an edit, by the stored rule's own kind.

        The rule's kind and period never change; ``name``, ``amount``,
        ``category`` and ``tags`` may. The stored row overlaid with ``fields``
        must pass the same :func:`rule_error` checks a new rule of its kind
        does. An edit that changes nothing is accepted as-is.

        Parameters
        ----------
        rule_id : int
            Rule id.
        kind : str, optional
            Restrict the edit to a rule of this kind (see :meth:`get`).
        **fields
            The fields to change.

        Raises
        ------
        ValidationException
            If a key is not editable, or the edited rule fails validation.
        EntityNotFoundException
            If no rule (of ``kind``) has that id.
        """
        if not set(fields) <= EDITABLE_FIELDS:
            raise ValidationException(
                f"Invalid fields for update. Valid fields: {EDITABLE_FIELDS}"
            )
        rules = self.all()
        row = self.get(rule_id, kind, rules)
        if NAME in fields:
            fields[NAME] = str(fields[NAME]).strip()
        name = fields.get(NAME, row[NAME])
        amount = fields.get(AMOUNT, row[AMOUNT])
        category = fields.get(CATEGORY, row[CATEGORY])
        tags = parse_tags(fields.get(TAGS, row[TAGS]))
        if TAGS in fields:
            fields[TAGS] = ";".join(tags)

        unchanged = (
            name == row[NAME]
            and amount == row[AMOUNT]
            and category == row[CATEGORY]
            and tags == row[TAGS]
        )
        if not unchanged:
            year = None if pd.isnull(row[YEAR]) else int(row[YEAR])
            month = None if pd.isnull(row[MONTH]) else int(row[MONTH])
            error = rule_error(
                rules,
                row[PERIOD_TYPE],
                name,
                category,
                tags,
                amount,
                year,
                month,
                rule_id,
            )
            if error is not None:
                raise ValidationException(error)
        self.repository.update(rule_id, **fields)

    def delete(self, rule_id: int, kind: str | None = None) -> None:
        """
        Delete a rule.

        A month's ``Total Budget`` rule and a project's ``all_tags`` total are
        the anchors their sibling rules are validated against, so they can't
        be removed on their own (the views already report them with
        ``allow_delete=False``) — delete the whole month or project.

        Raises
        ------
        ValidationException
            If the rule is a month's or a project's total.
        EntityNotFoundException
            If no rule (of ``kind``) has that id.
        """
        row = self.get(rule_id, kind)
        is_month_total = (
            row[PERIOD_TYPE] == PERIOD_MONTHLY and row[CATEGORY] == TOTAL_BUDGET
        )
        is_project_total = row[PERIOD_TYPE] == PERIOD_PROJECT and is_all_tags(row[TAGS])
        if is_month_total or is_project_total:
            raise ValidationException(
                "The Total Budget rule can't be deleted on its own. "
                "Delete the whole month or project instead."
            )
        self.repository.delete(rule_id)

    def find_conflicting_tags(
        self,
        category: str,
        tags: list[str],
        year: int,
        other_kind: str,
        *,
        exclude_rule_id: int | None = None,
    ) -> list[str]:
        """Return incoming tags that collide with ``other_kind`` rules; see :func:`conflicting_tags`."""
        return conflicting_tags(
            self.all(),
            category,
            tags,
            year,
            other_kind,
            exclude_rule_id=exclude_rule_id,
        )

    def strip_conflicting_tags(
        self,
        category: str,
        tags: list[str],
        year: int,
        other_kind: str,
    ) -> tuple[list[str], list[str]]:
        """Split ``tags`` into (kept, skipped) for auto-fill/carry-forward.

        Skipped tags are those that conflict with ``other_kind`` rules for the
        same category+year. If the incoming rule is ``all_tags`` and conflicts,
        all-tags is treated as fully skipped (returns ``([], ["all_tags"])``).
        """
        conflicts = set(self.find_conflicting_tags(category, tags, year, other_kind))
        if not conflicts:
            return list(tags), []
        if is_all_tags(tags):
            return [], [ALL_TAGS]
        kept = [t for t in tags if t not in conflicts]
        skipped = [t for t in tags if t in conflicts]
        return kept, skipped

    def is_category_project_owned(self, category: str) -> bool:
        """Return whether any project rule uses ``category``."""
        return category in project_categories(self.all())

    def category_used_by_monthly_or_yearly(self, category: str) -> bool:
        """Return whether any monthly or yearly rule uses ``category``."""
        return category in budgeted_categories(self.all())

    def find_category_overlaps(self) -> list[dict[str, Any]]:
        """Find categories that are BOTH project-owned and budget-used.

        Returns
        -------
        list[dict[str, Any]]
            One entry per overlapping category:
            ``{"category": str, "kinds": [<"monthly"|"yearly">, ...]}`` — the
            non-project kinds that collide, sorted. Empty when there is no
            overlap.
        """
        rules = self.all()
        overlaps = []
        for cat in sorted(project_categories(rules)):
            kinds = sorted(
                set(
                    rules.loc[
                        (rules[CATEGORY] == cat)
                        & (rules[PERIOD_TYPE].isin([PERIOD_MONTHLY, PERIOD_YEARLY])),
                        PERIOD_TYPE,
                    ]
                )
            )
            if kinds:
                overlaps.append({"category": cat, "kinds": kinds})
        return overlaps
