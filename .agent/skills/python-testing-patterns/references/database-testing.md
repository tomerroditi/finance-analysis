# Database Testing Patterns

Reference guide for testing database operations with SQLAlchemy and pytest.

## In-Memory SQLite Testing

```python
# test_database_models.py
import pytest
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

Base = declarative_base()


class User(Base):
    """User model."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(50))
    email = Column(String(100), unique=True)


@pytest.fixture(scope="function")
def db_session() -> Session:
    """Create in-memory database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


def test_create_user(db_session):
    """Test creating a user."""
    user = User(name="Test User", email="test@example.com")
    db_session.add(user)
    db_session.commit()

    assert user.id is not None
    assert user.name == "Test User"


def test_query_user(db_session):
    """Test querying users."""
    user1 = User(name="User 1", email="user1@example.com")
    user2 = User(name="User 2", email="user2@example.com")

    db_session.add_all([user1, user2])
    db_session.commit()

    users = db_session.query(User).all()
    assert len(users) == 2


def test_unique_email_constraint(db_session):
    """Test unique email constraint."""
    from sqlalchemy.exc import IntegrityError

    user1 = User(name="User 1", email="same@example.com")
    user2 = User(name="User 2", email="same@example.com")

    db_session.add(user1)
    db_session.commit()

    db_session.add(user2)

    with pytest.raises(IntegrityError):
        db_session.commit()
```

## Session-Scoped Database Fixture

For tests that need shared state across a module:

```python
@pytest.fixture(scope="module")
def db_engine():
    """Create database engine once per module."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create new session for each test with rollback."""
    connection = db_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()
```

## Testing Repository Pattern

```python
# test_user_repository.py
import pytest
from backend.repositories.user_repository import UserRepository
from backend.models import User


@pytest.fixture
def user_repository(db_session):
    """Provide repository with test session."""
    return UserRepository(db_session)


def test_create_user(user_repository, db_session):
    """Test repository create method."""
    user = user_repository.create(name="Test", email="test@example.com")
    
    assert user.id is not None
    
    # Verify in database
    found = db_session.query(User).filter_by(id=user.id).first()
    assert found is not None


def test_find_by_email(user_repository):
    """Test finding user by email."""
    user_repository.create(name="Test", email="find@example.com")
    
    found = user_repository.find_by_email("find@example.com")
    assert found is not None
    assert found.name == "Test"


def test_find_by_email_not_found(user_repository):
    """Test when email doesn't exist."""
    found = user_repository.find_by_email("nonexistent@example.com")
    assert found is None
```

## Database Fixture with Transactions

Pattern for automatic rollback after each test:

```python
@pytest.fixture
def db_session():
    """Session with automatic rollback."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    
    connection = engine.connect()
    transaction = connection.begin()
    
    Session = sessionmaker(bind=connection)
    session = Session()
    
    yield session
    
    # Rollback everything
    session.close()
    transaction.rollback()
    connection.close()
```

## Testing with Factory Boy

```python
# conftest.py
import factory
from factory.alchemy import SQLAlchemyModelFactory

class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session_persistence = "commit"

    name = factory.Faker("name")
    email = factory.Faker("email")


@pytest.fixture
def user_factory(db_session):
    """Provide factory bound to test session."""
    UserFactory._meta.sqlalchemy_session = db_session
    return UserFactory


# In tests
def test_with_factory(user_factory):
    user = user_factory.create()
    assert user.id is not None
    
    # Create batch
    users = user_factory.create_batch(5)
    assert len(users) == 5
```

## Tips

1. **Use in-memory SQLite** for fast, isolated tests
2. **Scope fixtures appropriately** - `function` for isolation, `module`/`session` for expensive setup
3. **Use transactions with rollback** for test isolation without recreating tables
4. **Consider Factory Boy** for generating test data
5. **Test constraints** (unique, foreign key, not null) explicitly
