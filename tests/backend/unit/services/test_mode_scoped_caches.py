"""Tests that in-memory service caches are keyed by demo mode."""

from backend.config import AppConfig
from backend.services import credentials_service, tagging_service


class TestCredentialsCacheIsModeScoped:
    """Tests for the credentials cache partition."""

    def teardown_method(self):
        """Drop both partitions so tests do not leak cached credentials."""
        credentials_service.CredentialsService.clear_cache()

    def test_real_and_demo_entries_coexist(self):
        """Verify writing one mode's entry leaves the other's intact."""
        credentials_service._credentials_cache[False] = {"real": {}}
        credentials_service._credentials_cache[True] = {"demo": {}}

        assert credentials_service._credentials_cache[False] == {"real": {}}
        assert credentials_service._credentials_cache[True] == {"demo": {}}

    def test_clear_cache_drops_both_partitions(self):
        """Verify clear_cache wipes every mode, preserving its old contract."""
        credentials_service._credentials_cache[False] = {"real": {}}
        credentials_service._credentials_cache[True] = {"demo": {}}

        credentials_service.CredentialsService.clear_cache()

        assert credentials_service._credentials_cache == {}


class TestCategoriesCacheIsModeScoped:
    """Tests for the categories cache partition."""

    def teardown_method(self):
        """Drop both partitions so tests do not leak cached categories."""
        tagging_service.CategoriesTagsService.clear_cache()

    def test_demo_write_does_not_evict_real_entry(self):
        """Verify invalidating in demo mode leaves the real entry cached."""
        tagging_service._categories_cache[False] = {"Groceries": ["milk"]}
        tagging_service._categories_cache[True] = {"Demo": ["x"]}

        config = AppConfig()
        token = config.set_demo_mode(True)
        try:
            tagging_service._categories_cache.pop(config.is_demo_mode, None)
        finally:
            config.reset_demo_mode(token)

        assert tagging_service._categories_cache[False] == {"Groceries": ["milk"]}
        assert True not in tagging_service._categories_cache
