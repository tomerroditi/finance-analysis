"""
Tagging API routes.

Provides endpoints for category and tag management.
"""

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.tagging_service import CategoriesTagsService

router = APIRouter()


class CategoryCreate(BaseModel):
    name: str
    tags: List[str] = []


class TagCreate(BaseModel):
    category: str
    name: str


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
async def get_categories(db: Session = Depends(get_database)):
    """Get all categories and their tags."""
    return CategoriesTagsService(db).get_categories_and_tags()


@router.post("/categories")
async def add_category(category: CategoryCreate, db: Session = Depends(get_database)):
    """Add a new category."""
    CategoriesTagsService(db).add_category(category.name, category.tags)
    return {"status": "success"}


@router.delete("/categories/{name}")
async def delete_category(name: str, db: Session = Depends(get_database)):
    """Delete a category and its tags, nullifying them in the DB."""
    CategoriesTagsService(db).delete_category(name)
    return {"status": "success"}


@router.post("/tags")
async def create_tag(tag: TagCreate, db: Session = Depends(get_database)):
    """Add a tag to a category."""
    CategoriesTagsService(db).add_tag(tag.category, tag.name)
    return {"status": "success"}


@router.delete("/tags/{category}/{name}")
async def delete_tag(category: str, name: str, db: Session = Depends(get_database)):
    """Delete a tag from a category, nullifying it in the DB."""
    CategoriesTagsService(db).delete_tag(category, name)
    return {"status": "success"}


@router.post("/tags/relocate")
async def relocate_tag(data: TagRelocate, db: Session = Depends(get_database)):
    """Relocate a tag to a different category, reflecting in the DB."""
    CategoriesTagsService(db).reallocate_tag(
        data.old_category, data.new_category, data.tag
    )
    return {"status": "success"}


@router.get("/icons")
async def get_category_icons(db: Session = Depends(get_database)):
    """Get category icons mapping."""
    return CategoriesTagsService(db).get_categories_icons()


@router.put("/icons/{category}")
async def update_category_icon(
    category: str, icon: str, db: Session = Depends(get_database)
):
    """Update a category's icon."""
    changed = CategoriesTagsService(db).update_category_icon(category, icon)
    return {"status": "success", "changed": changed}


@router.post("/add-new-credit-card-tags")
async def add_new_credit_card_tags(db: Session = Depends(get_database)):
    """Add new credit card tags."""
    CategoriesTagsService(db).add_new_credit_card_tags()
    return {"status": "success"}
