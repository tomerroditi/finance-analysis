"""
Tagging API routes.

Provides endpoints for category and tag management.
"""

from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.repositories.tagging_repository import TaggingRepository
from backend.services.tagging_rules_service import TaggingRulesService


router = APIRouter()


class CategoryCreate(BaseModel):
    name: str
    tags: List[str] = []


class TagCreate(BaseModel):
    category: str
    name: str


class RuleCreate(BaseModel):
    name: str
    conditions: List[Dict[str, Any]]
    category: str
    tag: str
    priority: int = 1


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    conditions: Optional[List[Dict[str, Any]]] = None
    category: Optional[str] = None
    tag: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryDelete(BaseModel):
    name: str


class TagDelete(BaseModel):
    category: str
    name: str


class TagRelocate(BaseModel):
    old_category: str
    new_category: str
    tag: str


@router.get("/categories")
async def get_categories():
    """Get all categories and their tags."""
    return TaggingRepository.get_categories()


@router.post("/categories")
async def add_category(category: CategoryCreate):
    """Add a new category."""
    TaggingRepository.add_category(category.name, category.tags)
    return {"status": "success"}


@router.delete("/categories/{name}")
async def delete_category(name: str, db: Session = Depends(get_database)):
    """Delete a category and its tags, nullifying them in the DB."""
    TaggingRepository.delete_category(name)

    tx_repo = TransactionsRepository(db)
    tx_repo.nullify_category(name)

    return {"status": "success"}


@router.post("/tags")
async def create_tag(tag: TagCreate):
    """Add a tag to a category."""
    TaggingRepository.add_tag(tag.category, tag.name)
    return {"status": "success"}


@router.delete("/tags/{category}/{name}")
async def delete_tag(category: str, name: str, db: Session = Depends(get_database)):
    """Delete a tag from a category, nullifying it in the DB."""
    tx_repo = TransactionsRepository(db)
    tx_repo.nullify_category_and_tag(category, name)

    TaggingRepository.delete_tag(category, name)

    return {"status": "success"}


@router.post("/tags/relocate")
async def relocate_tag(data: TagRelocate, db: Session = Depends(get_database)):
    """Relocate a tag to a different category, reflecting in the DB."""
    TaggingRepository.relocate_tag(data.tag, data.old_category, data.new_category)

    tx_repo = TransactionsRepository(db)
    tx_repo.update_category_for_tag(data.old_category, data.new_category, data.tag)

    return {"status": "success"}


@router.get("/icons")
async def get_category_icons():
    """Get category icons mapping."""
    return TaggingRepository.get_categories_icons()


@router.put("/icons/{category}")
async def update_category_icon(category: str, icon: str):
    """Update a category's icon."""
    changed = TaggingRepository.update_category_icon(category, icon)
    return {"status": "success", "changed": changed}


@router.get("/rules")
async def get_tagging_rules(
    active_only: bool = True, db: Session = Depends(get_database)
):
    """Get all tagging rules."""
    service = TaggingRulesService(db)
    df = service.get_all_rules(active_only=active_only)
    return df.to_dict(orient="records")


@router.post("/rules")
async def create_tagging_rule(rule: RuleCreate, db: Session = Depends(get_database)):
    """Create a new tagging rule and apply it."""
    service = TaggingRulesService(db)
    rule_id, n_tagged = service.add_rule(
        name=rule.name,
        conditions=rule.conditions,
        category=rule.category,
        tag=rule.tag,
        priority=rule.priority,
    )
    return {"status": "success", "id": rule_id, "tagged_count": n_tagged}


@router.put("/rules/{rule_id}")
async def update_tagging_rule(
    rule_id: int, rule: RuleUpdate, db: Session = Depends(get_database)
):
    """Update an existing tagging rule."""
    service = TaggingRulesService(db)
    n_tagged = service.update_rule(rule_id, **rule.model_dump(exclude_none=True))
    return {"status": "success", "tagged_count": n_tagged}


@router.delete("/rules/{rule_id}")
async def delete_tagging_rule(rule_id: int, db: Session = Depends(get_database)):
    """Delete a tagging rule."""
    service = TaggingRulesService(db)
    service.delete_rule(rule_id)
    return {"status": "success"}


@router.post("/rules/apply")
async def apply_tagging_rules(db: Session = Depends(get_database)):
    """Manually trigger application of all active rules."""
    service = TaggingRulesService(db)
    count = service.apply_rules()
    return {"status": "success", "tagged_count": count}


@router.post("/rules/test")
async def test_tagging_rule(
    conditions: List[Dict[str, Any]], db: Session = Depends(get_database)
):
    """Test rule conditions against existing transactions."""
    service = TaggingRulesService(db)
    count, df = service.test_rule_against_transactions(conditions, limit=100)
    return {"match_count": count, "sample_matches": df.to_dict(orient="records")}
