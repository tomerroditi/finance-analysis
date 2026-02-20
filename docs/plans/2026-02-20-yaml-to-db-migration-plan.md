# YAML-to-DB Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate TaggingRepository and CredentialsRepository from YAML file storage to SQLite DB storage for architectural consistency.

**Architecture:** Two new SQLAlchemy models (Category, Credential) replace YAML file I/O. Categories store tags as a JSON list column. Credentials store non-sensitive fields as JSON; passwords remain in OS Keyring. Services keep their in-memory caches but write/read through DB repos instead of YAML.

**Tech Stack:** SQLAlchemy 2.0, SQLite, pytest, OS Keyring

---

### Task 1: Add Table Constants + Category Model

**Files:**
- Modify: `backend/constants/tables.py:5-48` (add CATEGORIES, CREDENTIALS to Tables enum)
- Create: `backend/models/category.py`
- Modify: `backend/models/__init__.py` (add Category import + export)
- Test: `tests/backend/unit/models/test_category_model.py`

**Step 1: Add enum values to Tables**

In `backend/constants/tables.py`, add two new members to the `Tables` enum after `BANK_BALANCES`:

```python
    CATEGORIES = "categories"
    CREDENTIALS = "credentials"
```

Update the docstring to mention the two new tables.

**Step 2: Create Category model**

Create `backend/models/category.py`:

```python
"""Category model for storing categories, tags, and icons."""

from sqlalchemy import Column, Integer, JSON, String

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class Category(Base, TimestampMixin):
    """Model for category with embedded tags list and optional icon."""

    __tablename__ = Tables.CATEGORIES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    tags = Column(JSON, nullable=False, default=list)
    icon = Column(String, nullable=True)
```

**Step 3: Register in models/__init__.py**

Add to `backend/models/__init__.py`:

```python
from backend.models.category import Category
```

And add `"Category"` to the `__all__` list under `# Other models`.

**Step 4: Write model test**

Create `tests/backend/unit/models/test_category_model.py`:

```python
"""Unit tests for the Category ORM model."""

import pytest
from sqlalchemy.exc import IntegrityError

from backend.models.category import Category


class TestCategoryModel:
    """Tests for Category model constraints and defaults."""

    def test_create_category_with_tags(self, db_session):
        """Verify category created with name, tags list, and icon."""
        cat = Category(name="Food", tags=["Groceries", "Restaurants"], icon="🍔")
        db_session.add(cat)
        db_session.commit()
        db_session.refresh(cat)

        assert cat.id is not None
        assert cat.name == "Food"
        assert cat.tags == ["Groceries", "Restaurants"]
        assert cat.icon == "🍔"
        assert cat.created_at is not None

    def test_create_category_defaults(self, db_session):
        """Verify default empty tags list and null icon."""
        cat = Category(name="Salary")
        db_session.add(cat)
        db_session.commit()
        db_session.refresh(cat)

        assert cat.tags == []
        assert cat.icon is None

    def test_unique_name_constraint(self, db_session):
        """Verify duplicate category name raises IntegrityError."""
        db_session.add(Category(name="Food", tags=[]))
        db_session.commit()

        db_session.add(Category(name="Food", tags=["Other"]))
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_name_not_nullable(self, db_session):
        """Verify null name raises IntegrityError."""
        db_session.add(Category(name=None, tags=[]))
        with pytest.raises(IntegrityError):
            db_session.commit()
```

**Step 5: Run tests**

```bash
poetry run pytest tests/backend/unit/models/test_category_model.py -v
```

Expected: 4 PASS

**Step 6: Commit**

```bash
git add backend/constants/tables.py backend/models/category.py backend/models/__init__.py tests/backend/unit/models/test_category_model.py
git commit -m "feat: add Category model and table constant"
```

---

### Task 2: Add Credential Model

**Files:**
- Create: `backend/models/credential.py`
- Modify: `backend/models/__init__.py` (add Credential import + export)
- Test: `tests/backend/unit/models/test_credential_model.py`

**Step 1: Create Credential model**

Create `backend/models/credential.py`:

```python
"""Credential model for storing provider account credentials."""

from sqlalchemy import Column, Integer, JSON, String, UniqueConstraint

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class Credential(Base, TimestampMixin):
    """Model for provider credentials with non-sensitive fields as JSON."""

    __tablename__ = Tables.CREDENTIALS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    service = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    account_name = Column(String, nullable=False)
    fields = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("service", "provider", "account_name", name="uq_credential"),
    )
```

**Step 2: Register in models/__init__.py**

Add to `backend/models/__init__.py`:

```python
from backend.models.credential import Credential
```

Add `"Credential"` to `__all__`.

**Step 3: Write model test**

Create `tests/backend/unit/models/test_credential_model.py`:

```python
"""Unit tests for the Credential ORM model."""

import pytest
from sqlalchemy.exc import IntegrityError

from backend.models.credential import Credential


class TestCredentialModel:
    """Tests for Credential model constraints and defaults."""

    def test_create_credential(self, db_session):
        """Verify credential created with service, provider, account, and fields."""
        cred = Credential(
            service="banks",
            provider="hapoalim",
            account_name="Main Account",
            fields={"userCode": "test_code", "num": "12345"},
        )
        db_session.add(cred)
        db_session.commit()
        db_session.refresh(cred)

        assert cred.id is not None
        assert cred.service == "banks"
        assert cred.provider == "hapoalim"
        assert cred.account_name == "Main Account"
        assert cred.fields == {"userCode": "test_code", "num": "12345"}
        assert cred.created_at is not None

    def test_default_empty_fields(self, db_session):
        """Verify fields defaults to empty dict."""
        cred = Credential(
            service="banks", provider="hapoalim", account_name="Test"
        )
        db_session.add(cred)
        db_session.commit()
        db_session.refresh(cred)

        assert cred.fields == {}

    def test_unique_constraint(self, db_session):
        """Verify duplicate service+provider+account_name raises IntegrityError."""
        db_session.add(
            Credential(service="banks", provider="hapoalim", account_name="Main")
        )
        db_session.commit()

        db_session.add(
            Credential(service="banks", provider="hapoalim", account_name="Main")
        )
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_different_accounts_same_provider(self, db_session):
        """Verify different account names for same provider are allowed."""
        db_session.add(
            Credential(service="banks", provider="hapoalim", account_name="Main")
        )
        db_session.add(
            Credential(service="banks", provider="hapoalim", account_name="Savings")
        )
        db_session.commit()

        creds = db_session.query(Credential).all()
        assert len(creds) == 2
```

**Step 4: Run tests**

```bash
poetry run pytest tests/backend/unit/models/test_credential_model.py -v
```

Expected: 4 PASS

**Step 5: Commit**

```bash
git add backend/models/credential.py backend/models/__init__.py tests/backend/unit/models/test_credential_model.py
git commit -m "feat: add Credential model"
```

---

### Task 3: Rewrite TaggingRepository (DB-backed)

**Files:**
- Modify: `backend/repositories/tagging_repository.py` (full rewrite)
- Rewrite: `tests/backend/unit/repositories/test_tagging_repository.py`

**Step 1: Write the new tests first**

Rewrite `tests/backend/unit/repositories/test_tagging_repository.py`. Tests now use `db_session` fixture instead of `tmp_path` / YAML files:

```python
"""Unit tests for TaggingRepository DB-backed category and tag CRUD operations."""

import pytest

from backend.errors import EntityAlreadyExistsException, EntityNotFoundException
from backend.models.category import Category
from backend.repositories.tagging_repository import TaggingRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded_repo(db_session):
    """Create a TaggingRepository with two seeded categories."""
    db_session.add(Category(name="Food", tags=["Groceries", "Restaurants"]))
    db_session.add(Category(name="Transport", tags=["Gas", "Parking"]))
    db_session.commit()
    return TaggingRepository(db_session)


@pytest.fixture
def empty_repo(db_session):
    """Create a TaggingRepository with no categories."""
    return TaggingRepository(db_session)


# ---------------------------------------------------------------------------
# Class 1: Read operations
# ---------------------------------------------------------------------------


class TestTaggingRepositoryRead:
    """Tests for reading categories from the database."""

    def test_get_categories(self, seeded_repo):
        """Verify get_categories returns dict of category name to tags list."""
        result = seeded_repo.get_categories()
        assert isinstance(result, dict)
        assert result["Food"] == ["Groceries", "Restaurants"]
        assert result["Transport"] == ["Gas", "Parking"]

    def test_get_categories_empty(self, empty_repo):
        """Verify get_categories returns empty dict when no categories exist."""
        result = empty_repo.get_categories()
        assert result == {}

    def test_get_categories_icons(self, db_session):
        """Verify get_categories_icons returns name-to-icon mapping."""
        db_session.add(Category(name="Food", tags=[], icon="🍔"))
        db_session.add(Category(name="Transport", tags=[], icon="🚗"))
        db_session.add(Category(name="Salary", tags=[], icon=None))
        db_session.commit()

        repo = TaggingRepository(db_session)
        icons = repo.get_categories_icons()
        assert icons == {"Food": "🍔", "Transport": "🚗"}

    def test_get_categories_icons_empty(self, empty_repo):
        """Verify get_categories_icons returns empty dict when no categories."""
        assert empty_repo.get_categories_icons() == {}


# ---------------------------------------------------------------------------
# Class 2: Category operations
# ---------------------------------------------------------------------------


class TestTaggingRepositoryCategoryOperations:
    """Tests for adding and deleting categories."""

    def test_add_category(self, seeded_repo):
        """Verify adding a new category persists it with tags."""
        seeded_repo.add_category("Health", ["Doctor", "Pharmacy"])
        result = seeded_repo.get_categories()
        assert "Health" in result
        assert result["Health"] == ["Doctor", "Pharmacy"]
        assert "Food" in result

    def test_add_category_with_icon(self, empty_repo):
        """Verify adding a category with an icon stores it."""
        empty_repo.add_category("Food", ["Groceries"], icon="🍔")
        icons = empty_repo.get_categories_icons()
        assert icons["Food"] == "🍔"

    def test_add_category_with_empty_tags(self, seeded_repo):
        """Verify adding a category with empty tag list succeeds."""
        seeded_repo.add_category("Salary", [])
        result = seeded_repo.get_categories()
        assert result["Salary"] == []

    def test_add_category_already_exists(self, seeded_repo):
        """Verify adding a duplicate category raises EntityAlreadyExistsException."""
        with pytest.raises(EntityAlreadyExistsException, match="Food"):
            seeded_repo.add_category("Food", ["NewTag"])

    def test_delete_category(self, seeded_repo):
        """Verify deleting an existing category removes it."""
        seeded_repo.delete_category("Food")
        result = seeded_repo.get_categories()
        assert "Food" not in result
        assert "Transport" in result

    def test_delete_category_not_found(self, seeded_repo):
        """Verify deleting a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            seeded_repo.delete_category("NonExistent")


# ---------------------------------------------------------------------------
# Class 3: Tag operations
# ---------------------------------------------------------------------------


class TestTaggingRepositoryTagOperations:
    """Tests for adding and deleting tags within categories."""

    def test_add_tag(self, seeded_repo):
        """Verify adding a tag to an existing category appends it."""
        seeded_repo.add_tag("Food", "Snacks")
        result = seeded_repo.get_categories()
        assert "Snacks" in result["Food"]

    def test_add_tag_already_exists(self, seeded_repo):
        """Verify adding a duplicate tag raises EntityAlreadyExistsException."""
        with pytest.raises(EntityAlreadyExistsException, match="Groceries"):
            seeded_repo.add_tag("Food", "Groceries")

    def test_add_tag_category_not_found(self, seeded_repo):
        """Verify adding a tag to a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            seeded_repo.add_tag("NonExistent", "SomeTag")

    def test_delete_tag(self, seeded_repo):
        """Verify deleting a tag removes it from the category."""
        seeded_repo.delete_tag("Food", "Groceries")
        result = seeded_repo.get_categories()
        assert "Groceries" not in result["Food"]
        assert result["Food"] == ["Restaurants"]

    def test_delete_tag_not_found(self, seeded_repo):
        """Verify deleting a nonexistent tag raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistentTag"):
            seeded_repo.delete_tag("Food", "NonExistentTag")

    def test_delete_tag_category_not_found(self, seeded_repo):
        """Verify deleting a tag from a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            seeded_repo.delete_tag("NonExistent", "SomeTag")


# ---------------------------------------------------------------------------
# Class 4: Relocate tag
# ---------------------------------------------------------------------------


class TestTaggingRepositoryRelocate:
    """Tests for moving tags between categories."""

    def test_relocate_tag(self, seeded_repo):
        """Verify relocating a tag moves it from old to new category."""
        seeded_repo.relocate_tag("Groceries", "Food", "Transport")
        result = seeded_repo.get_categories()
        assert "Groceries" not in result["Food"]
        assert "Groceries" in result["Transport"]

    def test_relocate_tag_old_category_not_found(self, seeded_repo):
        """Verify relocating from a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            seeded_repo.relocate_tag("SomeTag", "NonExistent", "Food")

    def test_relocate_tag_tag_not_in_old(self, seeded_repo):
        """Verify relocating a tag not in the old category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="MissingTag"):
            seeded_repo.relocate_tag("MissingTag", "Food", "Transport")

    def test_relocate_tag_new_category_not_found(self, seeded_repo):
        """Verify relocating to a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            seeded_repo.relocate_tag("Groceries", "Food", "NonExistent")

    def test_relocate_tag_already_in_new_category(self, db_session):
        """Verify relocating a tag already in new category does not duplicate."""
        db_session.add(Category(name="Food", tags=["Groceries", "Restaurants"]))
        db_session.add(Category(name="Shopping", tags=["Groceries", "Clothes"]))
        db_session.commit()
        repo = TaggingRepository(db_session)

        repo.relocate_tag("Groceries", "Food", "Shopping")
        result = repo.get_categories()
        assert "Groceries" not in result["Food"]
        assert result["Shopping"].count("Groceries") == 1


# ---------------------------------------------------------------------------
# Class 5: Icon operations
# ---------------------------------------------------------------------------


class TestTaggingRepositoryIcons:
    """Tests for category icon loading and updating."""

    def test_update_category_icon_new(self, seeded_repo):
        """Verify setting an icon on a category without one returns True."""
        result = seeded_repo.update_category_icon("Food", "🍔")
        assert result is True
        assert seeded_repo.get_categories_icons()["Food"] == "🍔"

    def test_update_category_icon_changed(self, db_session):
        """Verify changing an existing icon returns True."""
        db_session.add(Category(name="Food", tags=[], icon="🍔"))
        db_session.commit()
        repo = TaggingRepository(db_session)

        result = repo.update_category_icon("Food", "🍕")
        assert result is True
        assert repo.get_categories_icons()["Food"] == "🍕"

    def test_update_category_icon_same_value(self, db_session):
        """Verify updating an icon to the same value returns False."""
        db_session.add(Category(name="Food", tags=[], icon="🍔"))
        db_session.commit()
        repo = TaggingRepository(db_session)

        result = repo.update_category_icon("Food", "🍔")
        assert result is False

    def test_update_category_icon_not_found(self, seeded_repo):
        """Verify updating icon for nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            seeded_repo.update_category_icon("NonExistent", "❓")


# ---------------------------------------------------------------------------
# Class 6: Seeding from YAML
# ---------------------------------------------------------------------------


class TestTaggingRepositorySeeding:
    """Tests for seeding categories from YAML files."""

    def test_seed_from_yaml(self, db_session, tmp_path):
        """Verify seeding from YAML files populates DB correctly."""
        import yaml

        cat_path = str(tmp_path / "categories.yaml")
        icons_path = str(tmp_path / "icons.yaml")

        with open(cat_path, "w") as f:
            yaml.dump({"Food": ["Groceries"], "Salary": []}, f)
        with open(icons_path, "w") as f:
            yaml.dump({"Food": "🍔"}, f)

        repo = TaggingRepository(db_session)
        repo.seed_from_yaml(cat_path, icons_path)

        result = repo.get_categories()
        assert result == {"Food": ["Groceries"], "Salary": []}
        assert repo.get_categories_icons() == {"Food": "🍔"}

    def test_seed_skips_when_table_not_empty(self, seeded_repo, tmp_path):
        """Verify seeding is skipped when categories already exist."""
        import yaml

        cat_path = str(tmp_path / "categories.yaml")
        icons_path = str(tmp_path / "icons.yaml")

        with open(cat_path, "w") as f:
            yaml.dump({"NewCat": ["NewTag"]}, f)
        with open(icons_path, "w") as f:
            yaml.dump({}, f)

        seeded_repo.seed_from_yaml(cat_path, icons_path)

        result = seeded_repo.get_categories()
        assert "NewCat" not in result
        assert "Food" in result
```

**Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/backend/unit/repositories/test_tagging_repository.py -v
```

Expected: FAIL (TaggingRepository constructor doesn't accept db_session yet)

**Step 3: Rewrite the TaggingRepository implementation**

Replace `backend/repositories/tagging_repository.py` entirely:

```python
"""Tagging repository for category and tag management.

This repository handles DB-based storage for categories, tags, and icons.
"""

import os
from typing import Optional

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.errors import EntityAlreadyExistsException, EntityNotFoundException
from backend.models.category import Category

BACKEND_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CATEGORIES_PATH = os.path.join(
    BACKEND_PATH, "resources", "default_categories.yaml"
)
DEFAULT_CATEGORIES_ICONS_PATH = os.path.join(
    BACKEND_PATH, "resources", "categories_icons.yaml"
)


class TaggingRepository:
    """Repository for category and tag CRUD operations backed by SQLite."""

    def __init__(self, db: Session):
        self.db = db

    def _get_category(self, name: str) -> Category:
        """Fetch a category by name or raise EntityNotFoundException."""
        cat = self.db.execute(
            select(Category).where(Category.name == name)
        ).scalar_one_or_none()
        if cat is None:
            raise EntityNotFoundException(f"Category '{name}' not found")
        return cat

    def get_categories(self) -> dict[str, list[str]]:
        """Get all categories and their tags as a dict."""
        rows = self.db.execute(select(Category)).scalars().all()
        return {row.name: list(row.tags) for row in rows}

    def add_category(
        self, name: str, tags: list[str], icon: Optional[str] = None
    ) -> None:
        """Add a new category. Raises EntityAlreadyExistsException on duplicate."""
        existing = self.db.execute(
            select(Category).where(Category.name == name)
        ).scalar_one_or_none()
        if existing is not None:
            raise EntityAlreadyExistsException(
                f"Category '{name}' already exists"
            )
        self.db.add(Category(name=name, tags=tags, icon=icon))
        self.db.commit()

    def delete_category(self, name: str) -> None:
        """Delete a category. Raises EntityNotFoundException if not found."""
        cat = self._get_category(name)
        self.db.delete(cat)
        self.db.commit()

    def add_tag(self, category: str, tag: str) -> None:
        """Add a tag to a category's tags list."""
        cat = self._get_category(category)
        if tag in cat.tags:
            raise EntityAlreadyExistsException(
                f"Tag '{tag}' already exists in category '{category}'"
            )
        cat.tags = [*cat.tags, tag]
        self.db.commit()

    def delete_tag(self, category: str, tag: str) -> None:
        """Remove a tag from a category's tags list."""
        cat = self._get_category(category)
        if tag not in cat.tags:
            raise EntityNotFoundException(
                f"Tag '{tag}' not found in category '{category}'"
            )
        cat.tags = [t for t in cat.tags if t != tag]
        self.db.commit()

    def relocate_tag(
        self, tag: str, old_category: str, new_category: str
    ) -> None:
        """Move a tag from one category to another."""
        old_cat = self._get_category(old_category)
        if tag not in old_cat.tags:
            raise EntityNotFoundException(
                f"Tag '{tag}' not found in category '{old_category}'"
            )
        new_cat = self._get_category(new_category)

        old_cat.tags = [t for t in old_cat.tags if t != tag]
        if tag not in new_cat.tags:
            new_cat.tags = [*new_cat.tags, tag]
        self.db.commit()

    def get_categories_icons(self) -> dict[str, str]:
        """Get mapping of category names to icons (excludes nulls)."""
        rows = self.db.execute(select(Category)).scalars().all()
        return {row.name: row.icon for row in rows if row.icon is not None}

    def update_category_icon(self, category: str, icon: str) -> bool:
        """Update a category's icon. Returns False if unchanged."""
        cat = self._get_category(category)
        if cat.icon == icon:
            return False
        cat.icon = icon
        self.db.commit()
        return True

    def seed_from_yaml(
        self, categories_path: str, icons_path: str
    ) -> None:
        """Seed categories from YAML files if the table is empty.

        Parameters
        ----------
        categories_path : str
            Path to YAML file with {category_name: [tags]} structure.
        icons_path : str
            Path to YAML file with {category_name: icon_emoji} structure.
        """
        existing = self.db.execute(select(Category)).first()
        if existing is not None:
            return

        categories = {}
        if os.path.exists(categories_path):
            with open(categories_path, "r") as f:
                categories = yaml.safe_load(f) or {}

        icons = {}
        if os.path.exists(icons_path):
            with open(icons_path, "r") as f:
                icons = yaml.safe_load(f) or {}

        for name, tags in categories.items():
            self.db.add(
                Category(name=name, tags=tags or [], icon=icons.get(name))
            )
        self.db.commit()
```

**Step 4: Run tests**

```bash
poetry run pytest tests/backend/unit/repositories/test_tagging_repository.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add backend/repositories/tagging_repository.py tests/backend/unit/repositories/test_tagging_repository.py
git commit -m "refactor: rewrite TaggingRepository from YAML to DB storage"
```

---

### Task 4: Rewrite CredentialsRepository (DB-backed)

**Files:**
- Modify: `backend/repositories/credentials_repository.py` (full rewrite)
- Test: `tests/backend/unit/repositories/test_credentials_repository.py` (new file)

**Step 1: Write tests**

Create `tests/backend/unit/repositories/test_credentials_repository.py`:

```python
"""Unit tests for CredentialsRepository DB-backed credential CRUD operations."""

import pytest
from unittest.mock import patch, MagicMock

from backend.errors import EntityNotFoundException
from backend.models.credential import Credential
from backend.repositories.credentials_repository import CredentialsRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_KEYRING_SERVICE = "finance-analysis-app"


@pytest.fixture
def mock_keyring():
    """Mock the keyring module to avoid OS keyring access."""
    with patch("backend.repositories.credentials_repository.keyring") as mk:
        mk.get_password.return_value = "secret123"
        mk.set_password.return_value = None
        mk.delete_password.return_value = None
        yield mk


@pytest.fixture
def seeded_repo(db_session, mock_keyring):
    """Create a CredentialsRepository with two seeded credentials."""
    db_session.add(
        Credential(
            service="banks",
            provider="hapoalim",
            account_name="Main Account",
            fields={"userCode": "test_code"},
        )
    )
    db_session.add(
        Credential(
            service="credit_cards",
            provider="isracard",
            account_name="Account 1",
            fields={"id": "000000000", "card6Digits": "123456"},
        )
    )
    db_session.commit()
    return CredentialsRepository(db_session)


@pytest.fixture
def empty_repo(db_session, mock_keyring):
    """Create a CredentialsRepository with no credentials."""
    return CredentialsRepository(db_session)


# ---------------------------------------------------------------------------
# Class 1: Read operations
# ---------------------------------------------------------------------------


class TestCredentialsRepositoryRead:
    """Tests for reading credentials from the database."""

    def test_get_credentials(self, seeded_repo, mock_keyring):
        """Verify get_credentials returns fields merged with keyring password."""
        result = seeded_repo.get_credentials("banks", "hapoalim", "Main Account")
        assert result["userCode"] == "test_code"
        assert result["password"] == "secret123"

    def test_get_credentials_not_found(self, seeded_repo):
        """Verify get_credentials raises EntityNotFoundException for missing account."""
        with pytest.raises(EntityNotFoundException):
            seeded_repo.get_credentials("banks", "hapoalim", "Nonexistent")

    def test_list_accounts(self, seeded_repo):
        """Verify list_accounts returns flat list of all accounts."""
        accounts = seeded_repo.list_accounts()
        assert len(accounts) == 2
        tuples = {(a["service"], a["provider"], a["account_name"]) for a in accounts}
        assert ("banks", "hapoalim", "Main Account") in tuples
        assert ("credit_cards", "isracard", "Account 1") in tuples

    def test_list_accounts_empty(self, empty_repo):
        """Verify list_accounts returns empty list when no credentials."""
        assert empty_repo.list_accounts() == []

    def test_get_all_credentials(self, seeded_repo, mock_keyring):
        """Verify get_all_credentials returns nested dict with passwords."""
        result = seeded_repo.get_all_credentials()
        assert "banks" in result
        assert "hapoalim" in result["banks"]
        assert "Main Account" in result["banks"]["hapoalim"]
        assert result["banks"]["hapoalim"]["Main Account"]["password"] == "secret123"


# ---------------------------------------------------------------------------
# Class 2: Write operations
# ---------------------------------------------------------------------------


class TestCredentialsRepositoryWrite:
    """Tests for saving and deleting credentials."""

    def test_save_credentials_new(self, empty_repo, mock_keyring):
        """Verify saving a new credential stores fields in DB and password in keyring."""
        empty_repo.save_credentials(
            "banks", "hapoalim", "Main",
            {"userCode": "abc", "password": "mypass"},
        )

        accounts = empty_repo.list_accounts()
        assert len(accounts) == 1
        mock_keyring.set_password.assert_called_once()

    def test_save_credentials_upsert(self, seeded_repo, mock_keyring):
        """Verify saving to existing account updates fields."""
        seeded_repo.save_credentials(
            "banks", "hapoalim", "Main Account",
            {"userCode": "new_code", "password": "newpass"},
        )

        result = seeded_repo.get_credentials("banks", "hapoalim", "Main Account")
        assert result["userCode"] == "new_code"

    def test_save_credentials_extracts_otp_token(self, empty_repo, mock_keyring):
        """Verify otpLongTermToken is stored in keyring, not in DB fields."""
        empty_repo.save_credentials(
            "banks", "onezero", "Account",
            {"email": "test@example.com", "password": "pw", "otpLongTermToken": "token123"},
        )

        # Two keyring calls: password + otpLongTermToken
        assert mock_keyring.set_password.call_count == 2

        # Verify token not in DB fields
        result = empty_repo.get_credentials("banks", "onezero", "Account")
        assert "otpLongTermToken" not in result.get("fields", result)

    def test_delete_credentials(self, seeded_repo, mock_keyring):
        """Verify deleting a credential removes DB row and keyring entries."""
        seeded_repo.delete_credentials("banks", "hapoalim", "Main Account")

        accounts = seeded_repo.list_accounts()
        assert len(accounts) == 1
        assert mock_keyring.delete_password.called

    def test_delete_credentials_not_found(self, seeded_repo):
        """Verify deleting nonexistent credential raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException):
            seeded_repo.delete_credentials("banks", "hapoalim", "Nonexistent")


# ---------------------------------------------------------------------------
# Class 3: Migration from YAML
# ---------------------------------------------------------------------------


class TestCredentialsRepositoryMigration:
    """Tests for one-time YAML migration."""

    def test_migrate_from_yaml(self, empty_repo, tmp_path, mock_keyring):
        """Verify YAML credentials are migrated into DB."""
        import yaml

        creds = {
            "banks": {
                "hapoalim": {
                    "Main Account": {"userCode": "test_code", "password": ""},
                }
            },
            "credit_cards": {},
        }
        creds_path = str(tmp_path / "credentials.yaml")
        with open(creds_path, "w") as f:
            yaml.dump(creds, f)

        empty_repo.migrate_from_yaml(creds_path)

        accounts = empty_repo.list_accounts()
        assert len(accounts) == 1
        assert accounts[0]["provider"] == "hapoalim"

    def test_migrate_skips_when_table_not_empty(self, seeded_repo, tmp_path, mock_keyring):
        """Verify migration is skipped when credentials already exist."""
        import yaml

        creds = {"banks": {"leumi": {"New Account": {"userCode": "new"}}}}
        creds_path = str(tmp_path / "credentials.yaml")
        with open(creds_path, "w") as f:
            yaml.dump(creds, f)

        seeded_repo.migrate_from_yaml(creds_path)

        accounts = seeded_repo.list_accounts()
        assert not any(a["provider"] == "leumi" for a in accounts)
```

**Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/backend/unit/repositories/test_credentials_repository.py -v
```

Expected: FAIL

**Step 3: Rewrite CredentialsRepository**

Replace `backend/repositories/credentials_repository.py`:

```python
"""Credentials repository for secure credential storage.

This repository handles DB-based storage for credentials
and OS keyring for sensitive fields (passwords, OTP tokens).
"""

import os
from typing import Dict, List, Optional

import keyring
import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import AppConfig
from backend.errors import EntityNotFoundException
from backend.models.credential import Credential

_KEYRING_SERVICE = "finance-analysis-app"
_SENSITIVE_FIELDS = ("password", "otpLongTermToken")


class CredentialsRepository:
    """Repository for credential storage backed by SQLite + OS Keyring."""

    def __init__(self, db: Session):
        self.db = db

    @property
    def keyring_service(self) -> str:
        """Keyring service name, with test suffix in test mode."""
        service = _KEYRING_SERVICE
        if AppConfig().is_test_mode:
            service += "-test"
        return service

    def _keyring_key(
        self, service: str, provider: str, account_name: str, field: str
    ) -> str:
        """Generate a standardized keyring key."""
        return f"{service}:{provider}:{account_name}:{field}"

    def _find_credential(
        self, service: str, provider: str, account_name: str
    ) -> Credential:
        """Fetch a credential row or raise EntityNotFoundException."""
        cred = self.db.execute(
            select(Credential).where(
                Credential.service == service,
                Credential.provider == provider,
                Credential.account_name == account_name,
            )
        ).scalar_one_or_none()
        if cred is None:
            raise EntityNotFoundException(
                f"Credentials for {service} {provider} {account_name} not found"
            )
        return cred

    def get_credentials(
        self, service: str, provider: str, account_name: str
    ) -> Dict:
        """Get credentials for an account, merging in keyring password."""
        cred = self._find_credential(service, provider, account_name)
        result = dict(cred.fields)
        result["password"] = (
            keyring.get_password(
                self.keyring_service,
                self._keyring_key(service, provider, account_name, "password"),
            )
            or ""
        )
        return result

    def save_credentials(
        self,
        service: str,
        provider: str,
        account_name: str,
        credentials: Dict,
    ) -> None:
        """Save credentials: sensitive fields to keyring, rest to DB."""
        fields = dict(credentials)

        for sensitive_field in _SENSITIVE_FIELDS:
            value = fields.pop(sensitive_field, None)
            if value is not None:
                keyring.set_password(
                    self.keyring_service,
                    self._keyring_key(service, provider, account_name, sensitive_field),
                    value or "",
                )

        existing = self.db.execute(
            select(Credential).where(
                Credential.service == service,
                Credential.provider == provider,
                Credential.account_name == account_name,
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.fields = fields
        else:
            self.db.add(
                Credential(
                    service=service,
                    provider=provider,
                    account_name=account_name,
                    fields=fields,
                )
            )
        self.db.commit()

    def delete_credentials(
        self, service: str, provider: str, account_name: str
    ) -> None:
        """Delete a credential from DB and clean up keyring entries."""
        cred = self._find_credential(service, provider, account_name)
        self.db.delete(cred)
        self.db.commit()

        for field in ("password", "secret", "otp_key", "otpLongTermToken"):
            try:
                keyring.delete_password(
                    self.keyring_service,
                    self._keyring_key(service, provider, account_name, field),
                )
            except keyring.errors.PasswordDeleteError:
                pass

    def list_accounts(self) -> List[Dict[str, str]]:
        """Get a flat list of all configured accounts."""
        rows = self.db.execute(select(Credential)).scalars().all()
        return [
            {
                "service": row.service,
                "provider": row.provider,
                "account_name": row.account_name,
            }
            for row in rows
        ]

    def get_all_credentials(self) -> Dict:
        """Get all credentials as nested dict with keyring passwords filled in."""
        rows = self.db.execute(select(Credential)).scalars().all()
        result: Dict = {}
        for row in rows:
            result.setdefault(row.service, {}).setdefault(row.provider, {})
            fields = dict(row.fields)
            fields["password"] = (
                keyring.get_password(
                    self.keyring_service,
                    self._keyring_key(
                        row.service, row.provider, row.account_name, "password"
                    ),
                )
                or ""
            )
            result[row.service][row.provider][row.account_name] = fields
        return result

    def migrate_from_yaml(self, credentials_path: str) -> None:
        """One-time migration: import existing YAML credentials into DB.

        Skips if the credentials table already has data.
        Only imports non-sensitive fields; passwords remain in keyring.
        """
        existing = self.db.execute(select(Credential)).first()
        if existing is not None:
            return

        if not os.path.exists(credentials_path):
            return

        with open(credentials_path, "r") as f:
            all_creds = yaml.safe_load(f) or {}

        for service, providers in all_creds.items():
            if not isinstance(providers, dict):
                continue
            for provider, accounts in providers.items():
                if not isinstance(accounts, dict):
                    continue
                for account_name, fields in accounts.items():
                    if not isinstance(fields, dict):
                        continue
                    clean_fields = {
                        k: v
                        for k, v in fields.items()
                        if k not in _SENSITIVE_FIELDS
                    }
                    self.db.add(
                        Credential(
                            service=service,
                            provider=provider,
                            account_name=account_name,
                            fields=clean_fields,
                        )
                    )
        self.db.commit()
```

**Step 4: Run tests**

```bash
poetry run pytest tests/backend/unit/repositories/test_credentials_repository.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add backend/repositories/credentials_repository.py tests/backend/unit/repositories/test_credentials_repository.py
git commit -m "refactor: rewrite CredentialsRepository from YAML/singleton to DB storage"
```

---

### Task 5: Update CategoriesTagsService

**Files:**
- Modify: `backend/services/tagging_service.py`

**Step 1: Update the service**

Key changes to `backend/services/tagging_service.py`:
- Constructor requires `db: Session` (remove `Optional`)
- Instantiate `TaggingRepository(db)` and use instance methods instead of static calls
- Remove `save_categories_and_tags()` — each repo method now commits individually
- Replace `TaggingRepository.get_categories()` static calls with `self.tagging_repo.get_categories()`
- Replace `TaggingRepository.get_categories_icons()` with `self.tagging_repo.get_categories_icons()`
- Replace `TaggingRepository.update_category_icon(...)` with `self.tagging_repo.update_category_icon(...)`
- In `add_category`: replace `self.categories_and_tags[category] = tags` + `self.save_categories_and_tags()` with `self.tagging_repo.add_category(category, tags)`
- In `delete_category`: replace `del self.categories_and_tags[category]` + `self.save_categories_and_tags()` with `self.tagging_repo.delete_category(category)`
- In `add_tag`: replace `self.categories_and_tags[category].append(tag)` + `self.save_categories_and_tags()` with `self.tagging_repo.add_tag(category, tag)`
- In `delete_tag`: replace list remove + save with `self.tagging_repo.delete_tag(category, tag)`
- In `reallocate_tag`: replace list manipulation + save with `self.tagging_repo.relocate_tag(tag, old_category, new_category)`
- Cache invalidation: after each mutation, set `_categories_cache = None` then reload from `self.tagging_repo.get_categories()`
- The `db is None` branch for optional repos stays for backwards compatibility but the `TaggingRepository` always requires DB now

Here is the full updated file:

```python
"""Tagging service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for category and tag management.
"""

from copy import deepcopy
from typing import Optional

from sqlalchemy.orm import Session

from backend.constants.categories import PROTECTED_CATEGORIES
from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)
from backend.repositories.tagging_repository import TaggingRepository
from backend.repositories.tagging_rules_repository import TaggingRulesRepository
from backend.repositories.transactions_repository import (
    CreditCardRepository,
    TransactionsRepository,
)
from backend.utils.text_utils import to_title_case


def _sorted_unique(lst: list) -> list:
    """Create a sorted list of unique elements."""
    return sorted(list(set(lst)))


# In-memory cache for categories
_categories_cache: Optional[dict] = None


class CategoriesTagsService:
    """Service for managing categories and tags."""

    def __init__(self, db: Session):
        self.db = db
        self.tagging_repo = TaggingRepository(db)
        self.transactions_repo = TransactionsRepository(db)
        self.split_transactions_repo = SplitTransactionsRepository(db)
        self.tagging_rules_repo = TaggingRulesRepository(db)
        self.credit_card_repo = CreditCardRepository(db)
        self.categories_and_tags = self.get_categories_and_tags()

    def get_categories_and_tags(self, copy: bool = False) -> dict[str, list[str]]:
        """Load categories and tags with caching."""
        global _categories_cache

        if _categories_cache is None:
            _categories_cache = self.tagging_repo.get_categories()

        if copy:
            return deepcopy(_categories_cache)
        return _categories_cache

    def _invalidate_cache(self) -> None:
        """Clear cache and reload from DB."""
        global _categories_cache
        _categories_cache = None
        self.categories_and_tags = self.get_categories_and_tags()

    @staticmethod
    def clear_cache() -> None:
        """Clear the in-memory categories cache."""
        global _categories_cache
        _categories_cache = None

    def get_categories_icons(self) -> dict[str, str]:
        """Load category icons."""
        return self.tagging_repo.get_categories_icons()

    def update_category_icon(self, category: str, icon: str) -> bool:
        """Set or update the icon for a category."""
        return self.tagging_repo.update_category_icon(category, icon)

    def add_category(self, category: str, tags: list[str]) -> bool:
        """Add a new category. Returns True if added successfully."""
        if not category or not isinstance(category, str) or not category.strip():
            return False
        category = to_title_case(category.strip())
        if category.lower() in [k.lower() for k in self.categories_and_tags.keys()]:
            return False
        self.tagging_repo.add_category(category, tags)
        self._invalidate_cache()
        return True

    def delete_category(self, category: str) -> bool:
        """Delete a category. Returns True if deleted successfully."""
        if category in PROTECTED_CATEGORIES:
            return False

        self.transactions_repo.nullify_category(category)
        self.split_transactions_repo.nullify_category(category)
        self.tagging_rules_repo.delete_rules_by_category(category)

        if category not in self.categories_and_tags:
            return False
        self.tagging_repo.delete_category(category)
        self._invalidate_cache()
        return True

    def reallocate_tag(self, old_category: str, new_category: str, tag: str) -> bool:
        """Move a tag from one category to another."""
        if (
            old_category not in self.categories_and_tags
            or new_category not in self.categories_and_tags
        ):
            return False

        self.transactions_repo.update_category_for_tag(
            old_category, new_category, tag
        )
        self.split_transactions_repo.update_category_for_tag(
            old_category, new_category, tag
        )
        self.tagging_rules_repo.update_category_for_tag(
            old_category, new_category, tag
        )

        self.tagging_repo.relocate_tag(tag, old_category, new_category)
        self._invalidate_cache()
        return True

    def add_tag(self, category: str, tag: str) -> bool:
        """Add a new tag to a category."""
        if category not in self.categories_and_tags:
            return False
        tag = to_title_case(tag.strip()) if tag else tag
        if tag in self.categories_and_tags[category]:
            return False
        self.tagging_repo.add_tag(category, tag)
        self._invalidate_cache()
        return True

    def delete_tag(self, category: str, tag: str) -> bool:
        """Delete a tag from a category."""
        self.transactions_repo.nullify_category_and_tag(category, tag)
        self.split_transactions_repo.nullify_category_and_tag(category, tag)
        self.tagging_rules_repo.delete_rules_by_category_and_tag(category, tag)

        if category not in self.categories_and_tags:
            return False
        if tag not in self.categories_and_tags[category]:
            return False
        self.tagging_repo.delete_tag(category, tag)
        self._invalidate_cache()
        return True

    def add_new_credit_card_tags(self) -> bool:
        """Add new credit card tags to the Credit Cards category."""
        cc_accounts = self.credit_card_repo.get_unique_accounts_tags()
        if "Credit Cards" not in self.categories_and_tags:
            self.add_category("Credit Cards", cc_accounts)
            return True
        for account in cc_accounts:
            self.add_tag("Credit Cards", account)
        return True
```

**Step 2: Run existing service tests (may need updates)**

```bash
poetry run pytest tests/backend/unit/services/ -k "tagging" -v
```

Fix any failures due to the constructor change (db is now required, not optional).

**Step 3: Commit**

```bash
git add backend/services/tagging_service.py
git commit -m "refactor: update CategoriesTagsService to use DB-backed TaggingRepository"
```

---

### Task 6: Update CredentialsService

**Files:**
- Modify: `backend/services/credentials_service.py`
- Modify: `tests/backend/unit/services/test_credentials_service.py`

**Step 1: Update CredentialsService**

Key changes:
- Constructor takes `db: Session`, instantiates `CredentialsRepository(db)`
- Remove `generate_keyring_key()` — repo owns key format
- `load_credentials()` calls `self.repository.get_all_credentials()` instead of reading YAML
- `save_credentials()` iterates the nested dict and calls `self.repository.save_credentials()` per account
- `get_safe_credentials()` uses `self.repository.list_accounts()` to build the nested dict
- `get_accounts_list()` delegates to `self.repository.list_accounts()`
- `delete_credential()` delegates to `self.repository.delete_credentials()`
- `delete_account()` delegates to `self.repository.delete_credentials()`
- Remove `_cleanup_empty_entries()` — no longer needed (DB handles empty state naturally)
- `seed_test_credentials()` calls `self.repository.save_credentials()` per test account

Here is the full updated file:

```python
"""Credentials service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for credential management.
"""

from copy import deepcopy
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from backend.config import AppConfig
from backend.constants.providers import Fields, bank_providers, cc_providers
from backend.repositories.credentials_repository import CredentialsRepository

# In-memory cache for credentials
_credentials_cache: Optional[Dict] = None


class CredentialsService:
    """Service for managing user credentials for financial services."""

    def __init__(self, db: Session):
        self.repository = CredentialsRepository(db)
        self.credentials = self.load_credentials()

    def load_credentials(self) -> Dict:
        """Load credentials with passwords from keyring."""
        global _credentials_cache

        if _credentials_cache is not None:
            return deepcopy(_credentials_cache)

        credentials = self.repository.get_all_credentials()
        _credentials_cache = credentials
        return deepcopy(credentials)

    def save_credentials(self, credentials: Dict) -> None:
        """Save credentials: passwords to keyring, fields to DB."""
        global _credentials_cache

        for service, providers in credentials.items():
            if not isinstance(providers, dict):
                continue
            for provider, accounts in providers.items():
                if not isinstance(accounts, dict):
                    continue
                for account_name, fields in accounts.items():
                    if not isinstance(fields, dict):
                        continue
                    if not fields or all(not v for v in fields.values()):
                        continue
                    self.repository.save_credentials(
                        service, provider, account_name, dict(fields)
                    )

        _credentials_cache = None
        self.credentials = self.load_credentials()

    def get_available_data_sources(self) -> List[str]:
        """Get a list of available services based on the credentials."""
        data_sources = []
        for service, providers in self.credentials.items():
            for provider, accounts in providers.items():
                for account in accounts.keys():
                    data_sources.append(f"{service} - {provider} - {account}")
        return data_sources

    def get_data_sources_credentials(self, data_sources: List[str]) -> Dict:
        """Filter credentials based on selected data sources."""
        credentials = deepcopy(self.credentials)

        for service, providers in list(credentials.items()):
            for provider, accounts in list(providers.items()):
                for account in list(accounts.keys()):
                    if f"{service} - {provider} - {account}" not in data_sources:
                        del credentials[service][provider][account]

                if not accounts:
                    del credentials[service][provider]

            if not providers:
                del credentials[service]

        return credentials

    def delete_account(self, service: str, provider: str, account: str) -> None:
        """Delete an account from the credentials."""
        self.repository.delete_credentials(service, provider, account)
        self._invalidate_cache()

    def get_scraper_credentials(self, service, provider, account) -> Dict:
        """Fetch credentials for a specific scraper or multiple scrapers."""
        credentials = deepcopy(self.credentials)

        services = [service] if isinstance(service, str) else service
        providers = [provider] if isinstance(provider, str) else provider
        accounts = [account] if isinstance(account, str) else account

        filtered = {}
        for svc in services:
            if svc not in credentials:
                continue
            filtered[svc] = {}
            for prov in providers:
                if prov not in credentials[svc]:
                    continue
                filtered[svc][prov] = {}
                for acc in accounts:
                    if acc in credentials[svc][prov]:
                        filtered[svc][prov][acc] = credentials[svc][prov][acc]

        return filtered

    def get_safe_credentials(self) -> Dict:
        """Get all credentials with sensitive data removed."""
        accounts = self.repository.list_accounts()
        safe: Dict = {}
        for a in accounts:
            safe.setdefault(a["service"], {}).setdefault(a["provider"], [])
            safe[a["service"]][a["provider"]].append(a["account_name"])
        return safe

    def get_accounts_list(self) -> List[Dict[str, str]]:
        """Get a flat list of all configured accounts."""
        return self.repository.list_accounts()

    @staticmethod
    def get_available_providers() -> Dict[str, List[str]]:
        """Get available providers filtered by test/production mode."""
        is_test = AppConfig().is_test_mode
        banks = [p for p in bank_providers if ("test_" in p) == is_test]
        ccs = [p for p in cc_providers if ("test_" in p) == is_test]
        return {"banks": banks, "credit_cards": ccs}

    def delete_credential(self, service: str, provider: str, account_name: str) -> None:
        """Delete a credential and clean up keyring entries."""
        self.repository.delete_credentials(service, provider, account_name)
        self._invalidate_cache()

    def seed_test_credentials(self) -> None:
        """Seed dummy credentials for test mode."""
        from backend.errors import EntityNotFoundException

        def ensure_dummy_cred(service, provider, account, creds_payload):
            try:
                self.repository.get_credentials(service, provider, account)
            except EntityNotFoundException:
                self.repository.save_credentials(
                    service, provider, account, creds_payload
                )
                self._invalidate_cache()

        ensure_dummy_cred(
            "banks", "test_bank", "Test Bank",
            {Fields.USERNAME.value: "test", Fields.PASSWORD.value: "password"},
        )
        ensure_dummy_cred(
            "banks", "test_bank_2fa", "Test Bank 2FA",
            {
                Fields.EMAIL.value: "test@example.com",
                Fields.PASSWORD.value: "password",
                Fields.PHONE_NUMBER.value: "12345678",
            },
        )
        ensure_dummy_cred(
            "credit_cards", "test_credit_card", "Test Credit Card",
            {Fields.USERNAME.value: "test", Fields.PASSWORD.value: "password"},
        )
        ensure_dummy_cred(
            "credit_cards", "test_credit_card_2fa", "Test Credit Card 2FA",
            {
                Fields.EMAIL.value: "test@example.com",
                Fields.PASSWORD.value: "password",
                Fields.PHONE_NUMBER.value: "12345678",
            },
        )

    def _invalidate_cache(self) -> None:
        """Clear cache and reload."""
        global _credentials_cache
        _credentials_cache = None
        self.credentials = self.load_credentials()

    @staticmethod
    def clear_cache() -> None:
        """Clear the in-memory credentials cache."""
        global _credentials_cache
        _credentials_cache = None
```

**Step 2: Update test file**

Rewrite `tests/backend/unit/services/test_credentials_service.py` to:
- Remove singleton reset logic (`CredentialsRepository._instance = None`, `_initialized = False`)
- Change `mock_repo` fixture: mock `CredentialsRepository` constructor to accept `db` session and return mock
- Update `monkeypatch.setattr` to `"backend.services.credentials_service.CredentialsRepository"` with a lambda that accepts `db` and returns the mock
- Remove tests for `generate_keyring_key` (method deleted)
- Update `test_save_credentials_stores_passwords_in_keyring` to match new save flow
- Update `test_delete_credential_cleans_keyring` — keyring keys now use `:` separator (repo handles cleanup)

Key fixture change:

```python
@pytest.fixture(autouse=True)
def reset_credentials_cache(monkeypatch):
    """Reset credentials cache between tests."""
    monkeypatch.setattr(cs, "_credentials_cache", None)
    yield
    monkeypatch.setattr(cs, "_credentials_cache", None)


@pytest.fixture
def mock_repo(monkeypatch):
    """Mock CredentialsRepository to avoid DB and keyring access."""
    mock = MagicMock()
    mock.get_all_credentials.return_value = deepcopy(SAMPLE_CREDENTIALS)
    mock.list_accounts.return_value = [
        {"service": "credit_cards", "provider": "isracard", "account_name": "Account 1"},
        {"service": "banks", "provider": "hapoalim", "account_name": "Main Account"},
    ]
    mock.save_credentials.return_value = None
    mock.delete_credentials.return_value = None

    monkeypatch.setattr(
        "backend.services.credentials_service.CredentialsRepository",
        lambda db: mock,
    )
    return mock
```

And update `CredentialsService()` calls to `CredentialsService(MagicMock())` (pass a mock db session).

**Step 3: Run tests**

```bash
poetry run pytest tests/backend/unit/services/test_credentials_service.py -v
```

**Step 4: Commit**

```bash
git add backend/services/credentials_service.py tests/backend/unit/services/test_credentials_service.py
git commit -m "refactor: update CredentialsService to use DB-backed CredentialsRepository"
```

---

### Task 7: Update Credentials Routes

**Files:**
- Modify: `backend/routes/credentials.py`
- Modify: `tests/backend/routes/test_credentials_routes.py` (if exists)

**Step 1: Update routes**

The credentials routes currently instantiate `CredentialsService()` without a db session and directly use `CredentialsRepository()`. Update all route handlers to:
- Accept `db: Session = Depends(get_database)` parameter
- Pass `db` to `CredentialsService(db)` and `CredentialsRepository(db)` (or remove direct repo usage in favor of service)

Key changes in `backend/routes/credentials.py`:
- `get_credentials()` → add `db: Session = Depends(get_database)`, use `CredentialsService(db)`
- `get_accounts()` → same
- `get_credential_details()` → use `CredentialsService(db)` instead of direct `CredentialsRepository()`
- `create_credential()` → use `CredentialsRepository(db)` or `CredentialsService(db)`
- `delete_credential()` → already has db, just pass to `CredentialsService(db)`
- Remove the direct `CredentialsRepository()` import if no longer used in routes

**Step 2: Run route tests**

```bash
poetry run pytest tests/backend/routes/test_credentials_routes.py -v
```

Fix any failures from the constructor changes.

**Step 3: Commit**

```bash
git add backend/routes/credentials.py tests/backend/routes/test_credentials_routes.py
git commit -m "refactor: update credentials routes to pass db session"
```

---

### Task 8: Add Startup Seeding/Migration Hooks

**Files:**
- Modify: `backend/main.py:39-46` (lifespan function)

**Step 1: Add seeding to lifespan**

Update the `lifespan` function in `backend/main.py` to seed categories and migrate credentials on startup:

```python
from backend.database import get_engine, SessionLocal
from backend.repositories.tagging_repository import (
    TaggingRepository,
    DEFAULT_CATEGORIES_PATH,
    DEFAULT_CATEGORIES_ICONS_PATH,
)
from backend.repositories.credentials_repository import CredentialsRepository
from backend.config import AppConfig


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    print("Starting Finance Analysis API...")
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    # Seed categories from YAML if DB table is empty
    db = SessionLocal()
    try:
        tagging_repo = TaggingRepository(db)
        # Prefer user's categories file if it exists, else use defaults
        user_categories_path = AppConfig().get_categories_path()
        categories_path = (
            user_categories_path
            if os.path.exists(user_categories_path)
            else DEFAULT_CATEGORIES_PATH
        )
        icons_path = DEFAULT_CATEGORIES_ICONS_PATH
        tagging_repo.seed_from_yaml(categories_path, icons_path)

        # Migrate credentials from YAML if DB table is empty
        creds_repo = CredentialsRepository(db)
        creds_repo.migrate_from_yaml(AppConfig().get_credentials_path())
    finally:
        db.close()

    yield
    print("Shutting down Finance Analysis API...")
```

You'll also need to import `SessionLocal` from `backend.database`. Check `backend/database.py` to confirm the session factory name — it may be `SessionLocal` or you may need to create a session from the engine.

**Step 2: Run full test suite to check nothing breaks**

```bash
poetry run pytest --tb=short -q
```

**Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: add startup seeding for categories and credentials migration"
```

---

### Task 9: Fix Remaining Tests and Integration

**Files:**
- Potentially modify: `tests/backend/routes/test_tagging_routes.py`
- Potentially modify: `tests/backend/integration/test_tagging_pipeline.py`
- Potentially modify: `tests/backend/unit/services/test_tagging_rules_service.py`
- Potentially modify: `tests/backend/conftest.py` (add `seed_categories` fixture)

**Step 1: Add seed_categories fixture**

Add to `tests/backend/conftest.py`:

```python
from backend.models.category import Category


@pytest.fixture
def seed_categories(db_session: Session) -> list:
    """Insert categories into the DB for tests that need them."""
    cats = [
        Category(name="Food", tags=["Groceries", "Restaurants", "Coffee"]),
        Category(name="Transport", tags=["Gas", "Parking", "Rides"]),
        Category(name="Entertainment", tags=["Cinema", "Streaming"]),
        Category(name="Salary", tags=[]),
        Category(name="Other Income", tags=["Prior Wealth"]),
        Category(name="Ignore", tags=["Transfer"]),
        Category(name="Investments", tags=["Stock Fund", "Bond Fund"]),
        Category(name="Liabilities", tags=["Mortgage"]),
        Category(name="Home", tags=["Cleaning", "Maintenance", "Rent"]),
        Category(name="Other", tags=[]),
        Category(name="Credit Cards", tags=[]),
    ]
    db_session.add_all(cats)
    db_session.commit()
    for c in cats:
        db_session.refresh(c)
    return cats
```

**Step 2: Run full test suite and fix failures**

```bash
poetry run pytest --tb=short 2>&1 | head -80
```

Common fixes needed:
- Tests that create `CategoriesTagsService(None)` → need to pass a real `db_session`
- Tests that create `CategoriesTagsService(db_session)` → may need `seed_categories` fixture so `get_categories_and_tags()` returns data
- Tests that mock `TaggingRepository` static methods → need to mock instance methods instead
- Route tests that call `CredentialsService()` → need mocking adjusted for `CredentialsService(db)` constructor

Iterate: fix failures, run again, until all pass.

**Step 3: Commit**

```bash
git add tests/
git commit -m "test: fix all tests for DB-backed tagging and credentials repos"
```

---

### Task 10: Cleanup Dead Code

**Files:**
- Delete: `backend/resources/default_credentials.yaml`
- Modify: `backend/config.py` (remove `get_credentials_path`, `get_categories_path`, `get_categories_icons_path` if no longer used)
- Verify: no remaining references to deleted methods

**Step 1: Search for remaining references**

Check if `get_credentials_path`, `get_categories_path`, `get_categories_icons_path` are still used anywhere (they may still be needed for the migration startup hook and for seeding):

```bash
# Search for usage
grep -r "get_credentials_path\|get_categories_path\|get_categories_icons_path" backend/ --include="*.py"
```

- `get_categories_path` — still used in `main.py` lifespan for seeding. Keep it.
- `get_credentials_path` — still used in `main.py` lifespan for migration. Keep it.
- `get_categories_icons_path` — no longer used (icons are in DB now). Can remove if confirmed.

**Step 2: Delete default_credentials.yaml**

```bash
rm backend/resources/default_credentials.yaml
```

**Step 3: Remove any unused imports in modified files**

Scan `tagging_service.py` and `credentials_service.py` for unused imports (e.g., `AppConfig` in tagging_service if no longer used).

**Step 4: Run full test suite one final time**

```bash
poetry run pytest --tb=short -q
```

Expected: All tests pass.

**Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove dead YAML code and default_credentials.yaml"
```

---

### Task 11: Final Verification

**Step 1: Run full test suite with coverage**

```bash
poetry run pytest --cov=backend --cov-report=term-missing -q
```

Verify coverage hasn't dropped significantly.

**Step 2: Start the dev server and verify startup seeding works**

```bash
poetry run uvicorn backend.main:app --reload
```

Check logs for successful startup (no errors about missing YAML files or DB tables).

**Step 3: Commit any final fixes**

If any issues found, fix and commit.
