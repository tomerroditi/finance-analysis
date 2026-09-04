"""Tests for the path-keyed SQLAlchemy engine registry."""

import threading

import backend.database as database


class TestEngineRegistry:
    """Tests that engines are cached per database path, not globally."""

    def teardown_method(self):
        """Drop every registry entry so tests do not leak engines."""
        database.reset_engines()

    def test_same_path_returns_same_engine(self, tmp_path):
        """Verify repeated calls for one path reuse a single engine."""
        db = str(tmp_path / "a.db")
        assert database.get_engine(db) is database.get_engine(db)

    def test_different_paths_return_different_engines(self, tmp_path):
        """Verify two paths get independent engines simultaneously."""
        a = database.get_engine(str(tmp_path / "a.db"))
        b = database.get_engine(str(tmp_path / "b.db"))
        assert a is not b

    def test_reset_engine_for_drops_only_that_path(self, tmp_path):
        """Verify targeted disposal leaves sibling engines intact."""
        path_a = str(tmp_path / "a.db")
        path_b = str(tmp_path / "b.db")
        a1 = database.get_engine(path_a)
        b1 = database.get_engine(path_b)

        database.reset_engine_for(path_a)

        assert database.get_engine(path_a) is not a1
        assert database.get_engine(path_b) is b1

    def test_reset_engines_drops_all(self, tmp_path):
        """Verify reset_engines invalidates every cached engine."""
        path_a = str(tmp_path / "a.db")
        a1 = database.get_engine(path_a)

        database.reset_engines()

        assert database.get_engine(path_a) is not a1

    def test_session_factory_bound_to_matching_engine(self, tmp_path):
        """Verify the factory for a path binds to that path's engine."""
        path = str(tmp_path / "a.db")
        factory = database.get_session_factory(path)
        assert factory.kw["bind"] is database.get_engine(path)

    def test_demo_and_real_resolve_to_different_engines(self, tmp_path):
        """Verify a demo context and a real context get separate engines."""
        from backend.config import AppConfig

        config = AppConfig()
        # AppConfig is a singleton, so this override outlives the test
        # unless it is restored — it would silently repoint every later
        # test at this tmp_path.
        previous = AppConfig._base_user_dir_override
        config._base_user_dir = str(tmp_path)
        try:
            real_engine = database.get_engine()
            token = config.set_demo_mode(True)
            try:
                demo_engine = database.get_engine()
            finally:
                config.reset_demo_mode(token)
            assert real_engine is not demo_engine
        finally:
            AppConfig._base_user_dir_override = previous

    def test_session_factory_never_bound_to_engine_absent_from_registry(
        self, tmp_path
    ):
        """Verify get_session_factory never returns a factory whose bound
        engine has already been dropped from ``_engines``.

        This is the invariant the engine/factory desync race breaks: if
        ``get_session_factory`` resolved the engine and the factory under
        two separate lock acquisitions, a ``reset_engines()`` landing in the
        gap between them could dispose the engine it already fetched and
        register a factory bound to that now-orphaned engine, while a later
        ``get_engine`` call would build (and register) a different one for
        the same path. Resolving both under one lock acquisition (via the
        ``_get_engine_locked`` helper) makes that window impossible —
        whatever engine a returned factory is bound to must still be the
        one registered for that path, checked atomically under the same
        lock the production code uses.
        """
        path = str(tmp_path / "a.db")
        for _ in range(200):
            factory = database.get_session_factory(path)
            with database._registry_lock:
                bound_engine = factory.kw["bind"]
                registered_engine = database._engines.get(path)
                assert bound_engine is registered_engine
            database.reset_engine_for(path)

    def test_concurrent_reset_never_desyncs_factory_from_engine(self, tmp_path):
        """Verify hammering get_session_factory concurrently with
        reset_engines never yields a factory bound to a dropped engine.

        Many threads race ``get_session_factory`` against ``reset_engines``
        for the same path. Each successful factory fetch immediately checks
        (holding the lock, same as the helper above) that its bound engine
        is still the one registered for the path — the exact invariant the
        two-lock-acquisition race in the old ``get_session_factory``
        violated. Run as many short iterations as possible rather than
        relying on sleeps, to make the race window likely to be hit without
        flakiness.
        """
        path = str(tmp_path / "a.db")
        iterations = 500
        errors = []

        def hammer_factory():
            for _ in range(iterations):
                factory = database.get_session_factory(path)
                with database._registry_lock:
                    bound_engine = factory.kw["bind"]
                    registered_engine = database._engines.get(path)
                    if bound_engine is not registered_engine:
                        errors.append((bound_engine, registered_engine))

        def hammer_reset():
            for _ in range(iterations):
                database.reset_engines()

        threads = [
            threading.Thread(target=hammer_factory),
            threading.Thread(target=hammer_factory),
            threading.Thread(target=hammer_reset),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
