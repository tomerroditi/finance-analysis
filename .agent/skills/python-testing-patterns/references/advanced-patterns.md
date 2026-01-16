# Advanced Testing Patterns

Reference guide for advanced testing patterns: async code, property-based testing, and custom markers.

## Testing Async Code

Requires `pytest-asyncio`:

```python
# test_async.py
import pytest
import asyncio

async def fetch_data(url: str) -> dict:
    """Fetch data asynchronously."""
    await asyncio.sleep(0.1)
    return {"url": url, "data": "result"}


@pytest.mark.asyncio
async def test_fetch_data():
    """Test async function."""
    result = await fetch_data("https://api.example.com")
    assert result["url"] == "https://api.example.com"
    assert "data" in result


@pytest.mark.asyncio
async def test_concurrent_fetches():
    """Test concurrent async operations."""
    urls = ["url1", "url2", "url3"]
    tasks = [fetch_data(url) for url in urls]
    results = await asyncio.gather(*tasks)

    assert len(results) == 3
    assert all("data" in r for r in results)


@pytest.fixture
async def async_client():
    """Async fixture."""
    client = {"connected": True}
    yield client
    client["connected"] = False


@pytest.mark.asyncio
async def test_with_async_fixture(async_client):
    """Test using async fixture."""
    assert async_client["connected"] is True
```

## Property-Based Testing with Hypothesis

Requires `hypothesis`:

```python
# test_properties.py
from hypothesis import given, strategies as st
import pytest

def reverse_string(s: str) -> str:
    """Reverse a string."""
    return s[::-1]


@given(st.text())
def test_reverse_twice_is_original(s):
    """Property: reversing twice returns original."""
    assert reverse_string(reverse_string(s)) == s


@given(st.text())
def test_reverse_length(s):
    """Property: reversed string has same length."""
    assert len(reverse_string(s)) == len(s)


@given(st.integers(), st.integers())
def test_addition_commutative(a, b):
    """Property: addition is commutative."""
    assert a + b == b + a


@given(st.lists(st.integers()))
def test_sorted_list_properties(lst):
    """Property: sorted list is ordered."""
    sorted_lst = sorted(lst)

    # Same length
    assert len(sorted_lst) == len(lst)

    # All elements present
    assert set(sorted_lst) == set(lst)

    # Is ordered
    for i in range(len(sorted_lst) - 1):
        assert sorted_lst[i] <= sorted_lst[i + 1]
```

### Hypothesis Strategies

```python
from hypothesis import given, strategies as st, assume, settings

# Common strategies
@given(st.integers(min_value=1, max_value=100))
def test_positive_integers(n):
    assert n > 0

@given(st.floats(allow_nan=False, allow_infinity=False))
def test_finite_floats(f):
    assert not (f != f)  # Not NaN

@given(st.dictionaries(st.text(), st.integers()))
def test_dict_operations(d):
    assert len(list(d.keys())) == len(d)

# Filtering with assume
@given(st.integers())
def test_non_zero_division(n):
    assume(n != 0)
    assert 10 / n is not None

# Custom settings
@settings(max_examples=200, deadline=None)
@given(st.text())
def test_with_more_examples(s):
    assert len(s) >= 0
```

## Custom Test Markers

### Defining Markers

```python
# pytest.ini or pyproject.toml
# [pytest]
# markers =
#     slow: marks tests as slow
#     integration: marks integration tests
#     sensitive: tests that access external services
```

### Using Markers

```python
import pytest
import os

@pytest.mark.slow
def test_slow_operation():
    """Mark slow tests."""
    import time
    time.sleep(2)


@pytest.mark.integration
def test_database_integration():
    """Mark integration tests."""
    pass


@pytest.mark.skip(reason="Feature not implemented yet")
def test_future_feature():
    """Skip tests temporarily."""
    pass


@pytest.mark.skipif(os.name == "nt", reason="Unix only test")
def test_unix_specific():
    """Conditional skip."""
    pass


@pytest.mark.xfail(reason="Known bug #123")
def test_known_bug():
    """Mark expected failures."""
    assert False


@pytest.mark.sensitive
def test_external_api():
    """Test that calls external API."""
    pass


# Run commands:
# pytest -m slow          # Run only slow tests
# pytest -m "not slow"    # Skip slow tests
# pytest -m integration   # Run integration tests
# pytest -m "not sensitive"  # Skip sensitive tests
```

## Parametrized Fixtures

```python
@pytest.fixture(params=["sqlite", "postgresql", "mysql"])
def db_backend(request):
    """Fixture that runs tests with different database backends."""
    return request.param


def test_with_db_backend(db_backend):
    """This test will run 3 times with different backends."""
    print(f"Testing with {db_backend}")
    assert db_backend in ["sqlite", "postgresql", "mysql"]


# Combine with indirect parametrization
@pytest.fixture
def api_client(request):
    """Fixture that accepts parameters."""
    version = request.param
    return {"version": version}


@pytest.mark.parametrize("api_client", ["v1", "v2"], indirect=True)
def test_api_versions(api_client):
    """Test runs with different API versions."""
    assert api_client["version"] in ["v1", "v2"]
```

## Testing Context Managers

```python
from contextlib import contextmanager

@contextmanager
def database_transaction(db):
    """Context manager for database transactions."""
    db.begin()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


def test_context_manager_success(mocker):
    """Test context manager commits on success."""
    mock_db = mocker.Mock()
    
    with database_transaction(mock_db):
        mock_db.execute("INSERT INTO users VALUES (1, 'Test')")
    
    mock_db.begin.assert_called_once()
    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_not_called()


def test_context_manager_rollback(mocker):
    """Test context manager rolls back on error."""
    mock_db = mocker.Mock()
    mock_db.execute.side_effect = Exception("DB Error")
    
    with pytest.raises(Exception, match="DB Error"):
        with database_transaction(mock_db):
            mock_db.execute("INVALID SQL")
    
    mock_db.rollback.assert_called_once()
```

## Tips

1. **Use `pytest-asyncio`** for testing async code with minimal boilerplate
2. **Property-based testing** catches edge cases you wouldn't think to test
3. **Custom markers** help organize and selectively run tests
4. **Parametrized fixtures** reduce duplication for multi-backend testing
5. **Set `deadline=None`** in Hypothesis for slow tests
