"""Tests that in-memory service caches are keyed by the resolved DB path.

Real mode, demo mode and every per-visitor demo sandbox resolve to a
different database file, so partitioning by path is what keeps one context
from ever serving another's cached categories or credentials.
"""

from backend.config import AppConfig
from backend.services import credentials_service, tagging_service


def _demo_key(session_id: str | None = None) -> str:
    """Return the cache key the demo context (optionally a sandbox) resolves to."""
    config = AppConfig()
    mode_token = config.set_demo_mode(True, ensure_dir=False)
    session_token = config.set_demo_session(session_id)
    try:
        return tagging_service.cache_key()
    finally:
        config.reset_demo_session(session_token)
        config.reset_demo_mode(mode_token)


class TestCacheKey:
    """Tests for the shared partition key."""

    def test_real_demo_and_sandbox_keys_differ(self):
        """Verify the three contexts never collide on one partition."""
        real = tagging_service.cache_key()
        demo = _demo_key()
        sandbox = _demo_key("visitor-0123456789abcdef")
        assert len({real, demo, sandbox}) == 3
        assert credentials_service.cache_key() == real


class TestCredentialsCacheIsPathScoped:
    """Tests for the credentials cache partition."""

    def teardown_method(self):
        """Drop every partition so tests do not leak cached credentials."""
        credentials_service.CredentialsService.clear_cache()

    def test_real_and_demo_entries_coexist(self):
        """Verify writing one context's entry leaves the other's intact."""
        real, demo = credentials_service.cache_key(), _demo_key()
        credentials_service._credentials_cache[real] = {"real": {}}
        credentials_service._credentials_cache[demo] = {"demo": {}}

        assert credentials_service._credentials_cache[real] == {"real": {}}
        assert credentials_service._credentials_cache[demo] == {"demo": {}}

    def test_clear_cache_drops_every_partition(self):
        """Verify clear_cache wipes every context, preserving its old contract."""
        credentials_service._credentials_cache[credentials_service.cache_key()] = {"real": {}}
        credentials_service._credentials_cache[_demo_key()] = {"demo": {}}

        credentials_service.CredentialsService.clear_cache()

        assert credentials_service._credentials_cache == {}

    def test_clear_cache_for_drops_only_that_path(self):
        """Verify a replaced sandbox file evicts its own entry and nothing else."""
        real, sandbox = credentials_service.cache_key(), _demo_key("visitor-0123456789abcdef")
        credentials_service._credentials_cache[real] = {"real": {}}
        credentials_service._credentials_cache[sandbox] = {"sandbox": {}}

        credentials_service.CredentialsService.clear_cache_for(sandbox)

        assert credentials_service._credentials_cache == {real: {"real": {}}}


class TestCategoriesCacheIsPathScoped:
    """Tests for the categories cache partition."""

    def teardown_method(self):
        """Drop every partition so tests do not leak cached categories."""
        tagging_service.CategoriesTagsService.clear_cache()

    def test_demo_write_does_not_evict_real_entry(self):
        """Verify invalidating in demo mode leaves the real entry cached."""
        real, demo = tagging_service.cache_key(), _demo_key()
        tagging_service._categories_cache[real] = {"Groceries": ["milk"]}
        tagging_service._categories_cache[demo] = {"Demo": ["x"]}

        config = AppConfig()
        token = config.set_demo_mode(True)
        try:
            tagging_service._categories_cache.pop(tagging_service.cache_key(), None)
        finally:
            config.reset_demo_mode(token)

        assert tagging_service._categories_cache[real] == {"Groceries": ["milk"]}
        assert demo not in tagging_service._categories_cache

    def test_sandbox_write_does_not_evict_shared_demo_entry(self):
        """Verify a visitor's sandbox has its own partition beside the shared demo DB."""
        demo, sandbox = _demo_key(), _demo_key("visitor-0123456789abcdef")
        tagging_service._categories_cache[demo] = {"Shared": []}
        tagging_service._categories_cache[sandbox] = {"Mine": []}

        tagging_service.CategoriesTagsService.clear_cache_for(sandbox)

        assert tagging_service._categories_cache == {demo: {"Shared": []}}
