"""
Tagging Rules API routes.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.errors import BadRequestException, EntityNotFoundException
from backend.services.tagging_rules_service import TaggingRulesService

router = APIRouter()


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
async def get_tagging_rules(db: Session = Depends(get_database)):
    """Get all tagging rules."""
    service = TaggingRulesService(db)
    df = service.get_all_rules()
    return df.to_dict(orient="records")


@router.post("/rules")
async def create_tagging_rule(rule: RuleCreate, db: Session = Depends(get_database)):
    """Create a new tagging rule and apply it."""
    service = TaggingRulesService(db)
    try:
        rule_id, n_tagged = service.add_rule(
            name=rule.name,
            conditions=rule.conditions,
            category=rule.category,
            tag=rule.tag,
        )
        return {"status": "success", "id": rule_id, "tagged_count": n_tagged}
    except BadRequestException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/rules/{rule_id}")
async def update_tagging_rule(
    rule_id: int, rule: RuleUpdate, db: Session = Depends(get_database)
):
    """Update an existing tagging rule."""
    service = TaggingRulesService(db)
    try:
        n_tagged = service.update_rule(rule_id, **rule.model_dump(exclude_none=True))
        return {"status": "success", "tagged_count": n_tagged}
    except EntityNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BadRequestException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/rules/{rule_id}")
async def delete_tagging_rule(rule_id: int, db: Session = Depends(get_database)):
    """Delete a tagging rule."""
    service = TaggingRulesService(db)
    try:
        service.delete_rule(rule_id)
        return {"status": "success"}
    except EntityNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/rules/apply")
async def apply_tagging_rules(
    overwrite: bool = True, db: Session = Depends(get_database)
):
    """Manually trigger application of all active rules."""
    service = TaggingRulesService(db)
    try:
        count = service.apply_rules(overwrite=overwrite)
        return {"status": "success", "tagged_count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rules/validate")
async def validate_rule_conflicts(
    rule: RuleValidate, db: Session = Depends(get_database)
):
    """Check for conflicts without saving."""
    service = TaggingRulesService(db)
    try:
        service.check_conflicts(
            conditions=rule.conditions,
            category=rule.category,
            tag=rule.tag,
            exclude_rule_id=rule.rule_id,
        )
        return {"status": "valid"}
    except BadRequestException as e:
        # Conflict is returned as 400
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
