"""
Tagging API routes.

Provides endpoints for category and tag management.
"""
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.repositories.tagging_repository import TaggingRepository, CATEGORIES_PATH
from backend.repositories.tagging_rules_repository import TaggingRulesRepository

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
    repo = TaggingRepository()
    if repo.file_exists(CATEGORIES_PATH):
        return repo.load_categories_from_file(CATEGORIES_PATH)
    return {}


@router.post("/categories")
async def create_category(category: CategoryCreate):
    """Create a new category."""
    repo = TaggingRepository()
    categories = {}
    if repo.file_exists(CATEGORIES_PATH):
        categories = repo.load_categories_from_file(CATEGORIES_PATH)
    
    if category.name in categories:
        # Update existing category tags if requested
        categories[category.name] = list(set(categories[category.name] + category.tags))
    else:
        categories[category.name] = category.tags
        
    repo.save_categories_to_file(categories, CATEGORIES_PATH)
    return {"status": "success"}


@router.delete("/categories/{name}")
async def delete_category(
    name: str,
    db: Session = Depends(get_database)
):
    """Delete a category and its tags, nullifying them in the DB."""
    repo = TaggingRepository()
    categories = {}
    if repo.file_exists(CATEGORIES_PATH):
        categories = repo.load_categories_from_file(CATEGORIES_PATH)
    
    if name not in categories:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Update DB
    tx_repo = TransactionsRepository(db)
    tx_repo.nullify_category(name)
    
    # Update YAML
    del categories[name]
    repo.save_categories_to_file(categories, CATEGORIES_PATH)
    
    return {"status": "success"}


@router.post("/tags")
async def create_tag(tag: TagCreate):
    """Add a tag to a category."""
    repo = TaggingRepository()
    categories = {}
    if repo.file_exists(CATEGORIES_PATH):
        categories = repo.load_categories_from_file(CATEGORIES_PATH)
    
    if tag.category not in categories:
        raise HTTPException(status_code=404, detail="Category not found")
    
    if tag.name in categories[tag.category]:
        raise HTTPException(status_code=400, detail="Tag already exists in category")
    
    categories[tag.category].append(tag.name)
    repo.save_categories_to_file(categories, CATEGORIES_PATH)
    return {"status": "success"}


@router.delete("/tags/{category}/{name}")
async def delete_tag(
    category: str,
    name: str,
    db: Session = Depends(get_database)
):
    """Delete a tag from a category, nullifying it in the DB."""
    repo = TaggingRepository()
    categories = {}
    if repo.file_exists(CATEGORIES_PATH):
        categories = repo.load_categories_from_file(CATEGORIES_PATH)
    
    if category not in categories or name not in categories[category]:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    # Update DB
    tx_repo = TransactionsRepository(db)
    tx_repo.nullify_category_and_tag(category, name)
    
    # Update YAML
    categories[category].remove(name)
    repo.save_categories_to_file(categories, CATEGORIES_PATH)
    
    return {"status": "success"}


@router.post("/tags/relocate")
async def relocate_tag(
    data: TagRelocate,
    db: Session = Depends(get_database)
):
    """Relocate a tag to a different category, reflecting in the DB."""
    repo = TaggingRepository()
    categories = {}
    if repo.file_exists(CATEGORIES_PATH):
        categories = repo.load_categories_from_file(CATEGORIES_PATH)
    
    if data.old_category not in categories or data.tag not in categories[data.old_category]:
        raise HTTPException(status_code=404, detail="Source category or tag not found")
    
    if data.new_category not in categories:
        raise HTTPException(status_code=404, detail="Destination category not found")

    if data.tag in categories[data.new_category]:
        raise HTTPException(status_code=400, detail="Tag already exists in destination category")

    # Update DB
    tx_repo = TransactionsRepository(db)
    tx_repo.update_category_for_tag(data.old_category, data.new_category, data.tag)
    
    # Update YAML
    categories[data.old_category].remove(data.tag)
    categories[data.new_category].append(data.tag)
    repo.save_categories_to_file(categories, CATEGORIES_PATH)
    
    return {"status": "success"}


@router.get("/icons")
async def get_category_icons():
    """Get category icons mapping."""
    return TaggingRepository.get_categories_icons()


@router.get("/rules")
async def get_tagging_rules(
    active_only: bool = True,
    db: Session = Depends(get_database)
):
    """Get all tagging rules."""
    from backend.services.tagging_rules_service import TaggingRulesService
    service = TaggingRulesService(db)
    df = service.get_all_rules(active_only=active_only)
    return df.to_dict(orient="records")


@router.post("/rules")
async def create_tagging_rule(
    rule: RuleCreate,
    db: Session = Depends(get_database)
):
    """Create a new tagging rule and apply it."""
    from backend.services.tagging_rules_service import TaggingRulesService
    service = TaggingRulesService(db)
    rule_id = service.add_rule(
        name=rule.name,
        conditions=rule.conditions,
        category=rule.category,
        tag=rule.tag,
        priority=rule.priority
    )
    return {"status": "success", "id": rule_id}


@router.put("/rules/{rule_id}")
async def update_tagging_rule(
    rule_id: int,
    rule: RuleUpdate,
    db: Session = Depends(get_database)
):
    """Update an existing tagging rule."""
    from backend.services.tagging_rules_service import TaggingRulesService
    service = TaggingRulesService(db)
    success = service.update_rule(rule_id, **rule.model_dump(exclude_none=True))
    return {"status": "success" if success else "no_changes"}


@router.delete("/rules/{rule_id}")
async def delete_tagging_rule(
    rule_id: int,
    db: Session = Depends(get_database)
):
    """Delete a tagging rule."""
    from backend.services.tagging_rules_service import TaggingRulesService
    service = TaggingRulesService(db)
    success = service.delete_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "success"}


@router.post("/rules/apply")
async def apply_tagging_rules(
    db: Session = Depends(get_database)
):
    """Manually trigger application of all active rules."""
    from backend.services.tagging_rules_service import TaggingRulesService
    service = TaggingRulesService(db)
    count = service.apply_rules()
    return {"status": "success", "tagged_count": count}


@router.post("/rules/test")
async def test_tagging_rule(
    conditions: List[Dict[str, Any]],
    db: Session = Depends(get_database)
):
    """Test rule conditions against existing transactions."""
    from backend.services.tagging_rules_service import TaggingRulesService
    service = TaggingRulesService(db)
    count, df = service.test_rule_against_transactions(conditions, limit=100)
    return {
        "match_count": count,
        "sample_matches": df.to_dict(orient="records")
    }
