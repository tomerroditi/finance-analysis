"""Tests that in-memory service caches are keyed by the resolved DB path.

Real mode, demo mode and every per-visitor demo sandbox resolve to a
different database file, so partitioning by path is what keeps one context
from ever serving another's cached categories or credentials.
"""

from contextlib import contextmanager

from backend.config import AppConfig
from backend.services import credentials_service, tagging_service

SANDBOX_ID = "visitor-0123456789abcdef"


@contextmanager
def _demo_context(session_id: str | None = None):
    """Bind demo mode (optionally a visitor sandbox) for the block's duration."""
    config = AppConfig()
    mode_token = config.set_demo_mode(True, ensure_dir=False)
    session_token = config.set_demo_session(session_id)
    try:
        yield
    finally:
        config.reset_demo_session(session_token)
        config.reset_demo_mode(mode_token)


def _demo_key(session_id: str | None = None) -> str:
    """Return the cache key the demo context (optionally a sandbox) resolves to."""
    with _demo_context(session_id):
        return tagging_service.cache_key()


class TestCacheKey:
    """Tests for the shared partition key."""

    def test_real_demo_and_sandbox_keys_differ(self):
        """Verify the three contexts never collide on one partition."""
        real = tagging_service.cache_key()
        demo = _demo_key()
        sandbox = _demo_key(SANDBOX_ID)
        assert len({real, demo, sandbox}) == 3
        assert credentials_service.cache_key() == real

    def test_two_sandboxes_get_their_own_partition(self):
        """Verify one visitor's key can never address another visitor's data."""
        assert _demo_key("visitor-aaaaaaaaaaaaaaaa") != _demo_key("visitor-bbbbbbbbbbbbbbbb")


class TestCredentialsCacheIsPathScoped:
    """Tests for the credentials cache partition."""

    def teardown_method(self):
        """Drop every partition so tests do not leak cached credentials."""
        credentials_service.CredentialsService.clear_cache()

    def test_sandbox_load_never_returns_another_context_entry(self, db_session):
        """Verify a visitor's request is not served the shared demo DB's cache.

        Goes through ``load_credentials`` rather than poking the dict, and
        uses the *shared demo* partition as the other context: keying by the
        demo-mode boolean (as this cache used to) put the shared copy and
        every visitor sandbox in the same bucket.
        """
        shared_demo = _demo_key()
        credentials_service._credentials_cache[shared_demo] = {"banks": {"leaked": {}}}

        with _demo_context(SANDBOX_ID):
            loaded = credentials_service.CredentialsService(db_session).load_credentials()

        assert "leaked" not in loaded.get("banks", {})
        assert credentials_service._credentials_cache[shared_demo] == {
            "banks": {"leaked": {}}
        }

    def test_clear_cache_drops_every_partition(self):
        """Verify clear_cache wipes every context, preserving its old contract."""
        credentials_service._credentials_cache[credentials_service.cache_key()] = {"real": {}}
        credentials_service._credentials_cache[_demo_key()] = {"demo": {}}

        credentials_service.CredentialsService.clear_cache()

        assert credentials_service._credentials_cache == {}

    def test_clear_cache_for_drops_only_that_path(self):
        """Verify a replaced sandbox file evicts its own entry and nothing else."""
        real, sandbox = credentials_service.cache_key(), _demo_key(SANDBOX_ID)
        credentials_service._credentials_cache[real] = {"real": {}}
        credentials_service._credentials_cache[sandbox] = {"sandbox": {}}

        credentials_service.CredentialsService.clear_cache_for(sandbox)

        assert credentials_service._credentials_cache == {real: {"real": {}}}


class TestCategoriesCacheIsPathScoped:
    """Tests for the categories cache partition."""

    def teardown_method(self):
        """Drop every partition so tests do not leak cached categories."""
        tagging_service.CategoriesTagsService.clear_cache()

    def test_demo_write_does_not_evict_real_entry(self, db_session):
        """Verify a demo-mode invalidation leaves the real entry cached.

        Calls the service's own ``_invalidate_cache`` — the code every
        category mutation runs — instead of evicting the entry by hand.
        """
        real, demo = tagging_service.cache_key(), _demo_key()
        tagging_service._categories_cache[real] = {"Groceries": ["milk"]}
        tagging_service._categories_cache[demo] = {"Demo": ["x"]}

        with _demo_context():
            tagging_service.CategoriesTagsService(db_session)._invalidate_cache()

        assert tagging_service._categories_cache[real] == {"Groceries": ["milk"]}
        assert tagging_service._categories_cache[demo] != {"Demo": ["x"]}

    def test_sandbox_read_never_returns_another_context_entry(self, db_session):
        """Verify a visitor's request is not served the shared demo DB's cache.

        The shared demo copy and every sandbox are all "demo mode", so this
        is the isolation that path-keying (rather than the old demo-mode
        boolean) buys.
        """
        shared_demo = _demo_key()
        tagging_service._categories_cache[shared_demo] = {"LeakedCategory": ["x"]}

        with _demo_context(SANDBOX_ID):
            loaded = tagging_service.CategoriesTagsService(db_session).get_categories_and_tags()

        assert "LeakedCategory" not in loaded
        assert tagging_service._categories_cache[shared_demo] == {"LeakedCategory": ["x"]}

    def test_sandbox_write_does_not_evict_shared_demo_entry(self):
        """Verify a visitor's sandbox has its own partition beside the shared demo DB."""
        demo, sandbox = _demo_key(), _demo_key(SANDBOX_ID)
        tagging_service._categories_cache[demo] = {"Shared": []}
        tagging_service._categories_cache[sandbox] = {"Mine": []}

        tagging_service.CategoriesTagsService.clear_cache_for(sandbox)

        assert tagging_service._categories_cache == {demo: {"Shared": []}}
