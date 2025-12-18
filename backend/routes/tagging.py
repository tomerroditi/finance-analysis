"""
Tagging API routes.

Provides endpoints for category and tag management.
"""
from typing import List

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
        raise HTTPException(status_code=400, detail="Category already exists")
    
    categories[category.name] = category.tags
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
    repo = TaggingRulesRepository(db)
    df = repo.get_all_rules(active_only=active_only)
    return df.to_dict(orient="records")
