"""Tests for the path-keyed SQLAlchemy engine registry."""

import sys
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

    def test_session_factory_bound_to_registered_engine_after_normal_call(
        self, tmp_path
    ):
        """Verify the ordinary, non-concurrent case: right after a plain
        ``get_session_factory`` call, the factory's bound engine is the
        engine registered for that path.

        This covers the single-threaded happy path only. It does NOT
        exercise the concurrent desync race the production fix (resolving
        the engine and the factory under one ``_registry_lock`` acquisition
        in ``_get_engine_locked``) protects against — a single-threaded test
        cannot race anything. See
        ``test_registry_engine_and_factory_never_disagree_under_concurrency``
        for the concurrent invariant check.
        """
        path = str(tmp_path / "a.db")
        factory = database.get_session_factory(path)
        with database._registry_lock:
            assert factory.kw["bind"] is database._engines.get(path)

    def test_registry_engine_and_factory_never_disagree_under_concurrency(
        self, tmp_path
    ):
        """Verify _engines and _session_factories never disagree for any
        path while the registry is under concurrent read/reset load.

        This checks the registry's internal consistency rather than the
        freshness of any single returned value. A factory fetched by
        ``get_session_factory`` at time T is bound to whatever engine was
        current at T; a concurrent reset can legitimately rotate the
        registry immediately afterwards, so asserting that a *previously
        returned* factory still matches the *current* registry is asserting
        something no correct concurrent design can guarantee (that was the
        flaw in the two tests this one replaces — they raced their own
        assertions against the registry rather than testing it).

        The real invariant the production fix guarantees is that the engine
        and factory for a path are always written together, under one
        ``_registry_lock`` acquisition (``_get_engine_locked`` called from
        inside ``get_session_factory``'s own lock scope) — so the two dicts
        can never disagree for a path present in both. A checker thread
        verifies exactly that: while holding ``_registry_lock``, for every
        path present in both ``_engines`` and ``_session_factories``, the
        factory's bound engine must be identical to the registered engine.
        Holding the lock across reading both dicts closes the only window
        that could make this racy, so the check itself is race-free.

        Worker threads hammer ``get_session_factory``/``get_engine`` for two
        paths while other threads reset the registry (targeted and full) in
        a tight loop; all loops use bounded iteration counts rather than
        sleeps. The race window this targets (the gap between
        ``get_session_factory`` releasing the lock inside its call to
        ``get_engine`` and re-acquiring it for the factory logic, in the
        pre-fix two-acquisition implementation) is only a couple of Python
        bytecodes wide, so the test temporarily shortens the interpreter's
        GIL switch interval (``sys.setswitchinterval``) to make the OS
        scheduler far more likely to preempt a thread inside that gap. This
        only changes how often threads are given a chance to interleave —
        it does not add any sleep/timing dependency to the assertions
        themselves, and the invariant checked is timing-independent: it must
        hold under the default interval too, just less reliably observably
        broken pre-fix within a bounded number of iterations.
        """
        paths = [str(tmp_path / "a.db"), str(tmp_path / "b.db")]
        iterations = 300
        checker_max_iterations = 20000
        violations = []
        stop = threading.Event()

        def hammer_session_factory(path):
            for _ in range(iterations):
                database.get_session_factory(path)

        def hammer_get_engine(path):
            for _ in range(iterations):
                database.get_engine(path)

        def hammer_reset():
            for i in range(iterations):
                if i % 2 == 0:
                    database.reset_engine_for(paths[i % len(paths)])
                else:
                    database.reset_engines()

        def checker():
            for _ in range(checker_max_iterations):
                if stop.is_set():
                    return
                with database._registry_lock:
                    for path, engine in database._engines.items():
                        factory = database._session_factories.get(path)
                        if factory is not None and factory.kw["bind"] is not engine:
                            violations.append(
                                {
                                    "path": path,
                                    "factory_bound_engine": factory.kw["bind"],
                                    "registered_engine": engine,
                                }
                            )

        checker_thread = threading.Thread(target=checker)
        worker_threads = [
            threading.Thread(target=hammer_session_factory, args=(paths[0],)),
            threading.Thread(target=hammer_session_factory, args=(paths[1],)),
            threading.Thread(target=hammer_get_engine, args=(paths[0],)),
            threading.Thread(target=hammer_get_engine, args=(paths[1],)),
            threading.Thread(target=hammer_reset),
        ]

        original_switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            checker_thread.start()
            for thread in worker_threads:
                thread.start()
            for thread in worker_threads:
                thread.join()
            stop.set()
            checker_thread.join()
        finally:
            sys.setswitchinterval(original_switch_interval)

        assert violations == []
