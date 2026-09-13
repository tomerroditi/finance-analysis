"""
Tagging API routes.

Provides endpoints for category and tag management.
"""

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.errors import EntityNotFoundException, ValidationException
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


class CategoryRename(BaseModel):
    new_name: str


class TagRename(BaseModel):
    new_name: str


@router.get("/categories")
def get_categories(db: Session = Depends(get_database)):
    """Get all categories and their tags."""
    return CategoriesTagsService(db).get_categories_and_tags()


@router.get("/categories/usage")
def get_category_usage(db: Session = Depends(get_database)):
    """Get per-category last-used date and whether the category is unused.

    A category is unused when it has had no transactions for six months, was
    created longer ago than that, and is not protected. Display-only — no
    other endpoint filters on this.
    """
    return CategoriesTagsService(db).get_category_usage()


@router.post("/categories")
def add_category(category: CategoryCreate, db: Session = Depends(get_database)):
    """Add a new category.

    Raises
    ------
    ValidationException
        400 if the name (or any tag) is blank or invalid, or the category
        already exists.
    """
    if not CategoriesTagsService(db).add_category(category.name, category.tags):
        raise ValidationException(
            f"Cannot add category '{category.name}'. The name may be blank or "
            "invalid, or the category may already exist."
        )
    return {"status": "success"}


@router.delete("/categories/{name}")
def delete_category(name: str, db: Session = Depends(get_database)):
    """Delete a category and all its tags.

    Transactions that were assigned to this category or any of its tags
    have their ``category`` and ``tag`` fields set to ``NULL`` in the DB.

    Raises
    ------
    EntityNotFoundException
        404 if no such category exists.
    ValidationException
        400 if the category is protected.
    """
    service = CategoriesTagsService(db)
    if not service.delete_category(name):
        if name not in service.categories_and_tags:
            raise EntityNotFoundException(f"Category '{name}' not found")
        raise ValidationException(f"Category '{name}' is protected and cannot be deleted")
    return {"status": "success"}


@router.post("/tags")
def create_tag(tag: TagCreate, db: Session = Depends(get_database)):
    """Add a tag to a category.

    Raises
    ------
    EntityNotFoundException
        404 if the category does not exist.
    ValidationException
        400 if the tag name is blank or invalid, or already exists.
    """
    service = CategoriesTagsService(db)
    if not service.add_tag(tag.category, tag.name):
        if tag.category not in service.categories_and_tags:
            raise EntityNotFoundException(f"Category '{tag.category}' not found")
        raise ValidationException(
            f"Cannot add tag '{tag.name}' to '{tag.category}'. The name may be "
            "blank or invalid, or the tag may already exist."
        )
    return {"status": "success"}


@router.delete("/tags/{category}/{name}")
def delete_tag(category: str, name: str, db: Session = Depends(get_database)):
    """Delete a tag from a category.

    Transactions tagged with this tag have their ``category`` and ``tag``
    fields set to ``NULL`` in the DB.

    Raises
    ------
    EntityNotFoundException
        404 if the category or tag does not exist.
    """
    if not CategoriesTagsService(db).delete_tag(category, name):
        raise EntityNotFoundException(f"Tag '{name}' not found in category '{category}'")
    return {"status": "success"}


@router.post("/tags/relocate")
def relocate_tag(data: TagRelocate, db: Session = Depends(get_database)):
    """Move a tag from one category to another.

    Re-categorises transactions, tagging rules and budget rules that carry
    this tag so their ``category`` reflects the new parent category.

    Raises
    ------
    EntityNotFoundException
        404 if either category, or the tag under ``old_category``, does not
        exist.
    ValidationException
        400 if both categories are the same.
    """
    service = CategoriesTagsService(db)
    if not service.reallocate_tag(data.old_category, data.new_category, data.tag):
        categories = service.categories_and_tags
        if data.old_category not in categories or data.new_category not in categories:
            raise EntityNotFoundException("Category not found")
        if data.tag not in categories[data.old_category]:
            raise EntityNotFoundException(
                f"Tag '{data.tag}' not found in category '{data.old_category}'"
            )
        raise ValidationException(
            f"Cannot move tag '{data.tag}' from '{data.old_category}' to itself"
        )
    return {"status": "success"}


@router.put("/categories/{name}")
def rename_category(name: str, data: CategoryRename, db: Session = Depends(get_database)):
    """Rename a category and cascade the change across all tables."""
    success = CategoriesTagsService(db).rename_category(name, data.new_name)
    if not success:
        raise ValidationException(
            f"Cannot rename category '{name}'. It may be protected, not found, or '{data.new_name}' already exists."
        )
    return {"status": "success"}


@router.put("/tags/{category}/{name}")
def rename_tag(category: str, name: str, data: TagRename, db: Session = Depends(get_database)):
    """Rename a tag and cascade the change across all tables."""
    success = CategoriesTagsService(db).rename_tag(category, name, data.new_name)
    if not success:
        raise ValidationException(
            f"Cannot rename tag '{name}'. It may be protected, not found, or '{data.new_name}' already exists in '{category}'."
        )
    return {"status": "success"}


@router.get("/icons")
def get_category_icons(db: Session = Depends(get_database)):
    """Get category icons mapping."""
    return CategoriesTagsService(db).get_categories_icons()


@router.put("/icons/{category}")
def update_category_icon(
    category: str, icon: str, db: Session = Depends(get_database)
):
    """Update a category's icon."""
    changed = CategoriesTagsService(db).update_category_icon(category, icon)
    return {"status": "success", "changed": changed}


@router.post("/add-new-credit-card-tags")
def add_new_credit_card_tags(db: Session = Depends(get_database)):
    """Discover credit card accounts from transaction data and register them as tags.

    Scans credit card transactions for unique provider/account combinations and
    adds each as a tag under the ``Credit Cards`` category. These tags are later
    used by the auto-tag credit card bills feature to match bank debit lines to
    the corresponding monthly credit card charges.
    """
    CategoriesTagsService(db).add_new_credit_card_tags()
    return {"status": "success"}
