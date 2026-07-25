"""
Tagging Rules API routes.

Provides endpoints to manage and apply auto-tagging rules. Rules are evaluated
in priority order (highest first); the first matching rule wins.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.errors import ValidationException
from backend.services.tagging_rules_service import TaggingRulesService

router = APIRouter()


def _validate_conditions(service: TaggingRulesService, conditions: dict) -> None:
    """Run the shared rule-integrity check on client-supplied conditions.

    ``add_rule``/``update_rule`` validate their conditions before touching
    the DB; the read-only endpoints did not, so malformed values (a
    non-numeric amount, ``null``, a one-element ``between``) reached the
    query builder and crashed it with a 500.

    Parameters
    ----------
    service : TaggingRulesService
        Service owning the integrity rules.
    conditions : dict
        Condition tree supplied by the client.

    Raises
    ------
    BadRequestException
        If the conditions violate the rule schema (mapped to HTTP 400).
    ValidationException
        If a condition value has a type the validator itself cannot coerce
        (e.g. ``null`` in a numeric comparison), also mapped to HTTP 400.
    """
    try:
        service.validate_rule_integrity(conditions)
    except (TypeError, ValueError) as e:
        raise ValidationException(f"Invalid rule conditions: {e}")


class RuleCreate(BaseModel):
    name: str
    conditions: Dict[str, Any]
    category: str
    tag: str


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    conditions: Optional[Dict[str, Any]] = None
    category: Optional[str] = None
    tag: Optional[str] = None
    priority: Optional[int] = None


class RuleValidate(BaseModel):
    conditions: Dict[str, Any]
    category: str
    tag: str
    rule_id: Optional[int] = None


@router.get("/rules")
def get_tagging_rules(db: Session = Depends(get_database)):
    """Get all tagging rules."""
    service = TaggingRulesService(db)
    df = service.get_all_rules()
    return df.to_dict(orient="records")


@router.post("/rules")
def create_tagging_rule(rule: RuleCreate, db: Session = Depends(get_database)):
    """Create a new tagging rule and immediately apply it to existing transactions.

    Returns
    -------
    dict
        ``{"status": "success", "id": int, "tagged_count": int}`` where
        ``tagged_count`` is the number of transactions tagged by the new rule.

    Raises
    ------
    HTTPException
        400 if the rule conditions conflict with an existing rule.
    """
    service = TaggingRulesService(db)
    rule_id, n_tagged = service.add_rule(
        name=rule.name,
        conditions=rule.conditions,
        category=rule.category,
        tag=rule.tag,
    )
    return {"status": "success", "id": rule_id, "tagged_count": n_tagged}


@router.put("/rules/{rule_id}")
def update_tagging_rule(
    rule_id: int, rule: RuleUpdate, db: Session = Depends(get_database)
):
    """Update an existing tagging rule and re-apply it.

    Returns
    -------
    dict
        ``{"status": "success", "tagged_count": int}`` where ``tagged_count``
        is the number of transactions tagged after the update.

    Raises
    ------
    HTTPException
        404 if the rule does not exist.
        400 if updated conditions conflict with another rule.
    """
    service = TaggingRulesService(db)
    n_tagged = service.update_rule(rule_id, **rule.model_dump(exclude_none=True))
    return {"status": "success", "tagged_count": n_tagged}


@router.delete("/rules/{rule_id}")
def delete_tagging_rule(rule_id: int, db: Session = Depends(get_database)):
    """Delete a tagging rule."""
    service = TaggingRulesService(db)
    service.delete_rule(rule_id)
    return {"status": "success"}


@router.post("/rules/apply")
def apply_tagging_rules(
    overwrite: bool = False, db: Session = Depends(get_database)
):
    """Manually trigger application of all active tagging rules.

    Parameters
    ----------
    overwrite : bool, optional
        When ``True``, re-tag already-tagged transactions.
        When ``False`` (default), only tag transactions with no category/tag.

    Returns
    -------
    dict
        ``{"status": "success", "tagged_count": int}``.
    """
    service = TaggingRulesService(db)
    count = service.apply_rules(overwrite=overwrite)
    return {"status": "success", "tagged_count": count}


@router.post("/rules/{rule_id}/apply")
def apply_single_tagging_rule(
    rule_id: int, overwrite: bool = False, db: Session = Depends(get_database)
):
    """Apply a single tagging rule to all transactions.

    Parameters
    ----------
    rule_id : int
        ID of the rule to apply.
    overwrite : bool, optional
        When ``True``, re-tag already-tagged transactions.
        When ``False`` (default), only tag untagged transactions.

    Raises
    ------
    HTTPException
        404 if the rule does not exist.
    """
    service = TaggingRulesService(db)
    count = service.apply_rule_by_id(rule_id, overwrite=overwrite)
    return {"status": "success", "tagged_count": count}


@router.post("/rules/validate")
def validate_rule_conflicts(
    rule: RuleValidate, db: Session = Depends(get_database)
):
    """Check whether a rule's conditions conflict with existing rules.

    Optionally excludes a specific rule from the conflict check (used when
    editing an existing rule to avoid self-conflict).

    Parameters
    ----------
    rule : RuleValidate
        ``conditions``, ``category``, ``tag`` to validate, and an optional
        ``rule_id`` to exclude from the conflict check.

    Returns
    -------
    dict
        ``{"status": "valid"}`` if no conflicts found.

    Raises
    ------
    HTTPException
        400 if a conflicting rule exists.
    """
    service = TaggingRulesService(db)
    _validate_conditions(service, rule.conditions)
    service.check_conflicts(
        conditions=rule.conditions,
        category=rule.category,
        tag=rule.tag,
        exclude_rule_id=rule.rule_id,
    )
    return {"status": "valid"}


class RulePreview(BaseModel):
    conditions: Dict[str, Any]
    # Bounded: an unbounded default returned the whole table, and a negative
    # limit made SQLite ignore the LIMIT while pandas ``head(-1)`` dropped a
    # row — a preview that silently lied about what the rule matches.
    limit: int = Field(default=100, ge=1, le=1000)


@router.post("/rules/preview")
def preview_rule_matches(
    preview: RulePreview, db: Session = Depends(get_database)
):
    """Preview which transactions would be matched by given rule conditions.

    Does not persist any changes — read-only dry run.

    Parameters
    ----------
    preview : RulePreview
        ``conditions`` dict defining match criteria and a ``limit`` (1-1000,
        default 100) capping the number of returned matches.

    Returns
    -------
    dict
        ``{"matches": list[dict], "count": int}``.

    Raises
    ------
    HTTPException
        400 if the conditions are malformed.
    """
    service = TaggingRulesService(db)
    _validate_conditions(service, preview.conditions)
    matches = service.preview_rule(preview.conditions, preview.limit)
    return {"matches": matches, "count": len(matches)}


@router.post("/rules/auto-tag-credit-cards-bills")
def auto_tag_credit_cards_bills(db: Session = Depends(get_database)):
    """Auto-tag bank transactions that represent credit card monthly bill payments.

    For each credit card account tag (discovered via ``add-new-credit-card-tags``),
    computes the monthly total charged to that card and finds the matching bank
    debit transaction (amount within ±0.01). When exactly one match is found it is
    tagged as ``Credit Cards / <account tag>``. Untagged bank transactions that
    don't match any card total are left untouched.

    Returns
    -------
    dict
        ``{"status": "success", "tagged_count": int}`` with the number of
        bank transactions successfully tagged.
    """
    service = TaggingRulesService(db)
    count = service.auto_tag_credit_cards_bills()
    return {"status": "success", "tagged_count": count}
