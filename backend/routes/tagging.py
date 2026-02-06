"""
Tagging API routes.

Provides endpoints for category and tag management.
"""

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.repositories.tagging_repository import TaggingRepository
from backend.repositories.transactions_repository import TransactionsRepository

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
