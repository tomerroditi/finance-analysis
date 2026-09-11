"""Tests for per-visitor demo sandboxes (``backend.demo_sessions``).

The store is exercised against an in-memory blob backend so every path —
restore from blob, clone from template, build from the frozen snapshot,
persist, reset, prune — runs without the network and without touching the
developer's real ``~/.finance-analysis``.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend import database, demo_sessions
from backend.config import AppConfig
from backend.demo_sessions import DemoSessionStore, blob_pathname, parse_session_id
from backend.utils import vercel_blob
from backend.utils.vercel_blob import BlobObject, BlobPutResult

SID_A = "visitor-aaaaaaaaaaaaaaaa"
SID_B = "visitor-bbbbbbbbbbbbbbbb"


class FakeBlobBackend:
    """Dict-backed stand-in for Vercel Blob with etag semantics.

    Every ``put`` mints a new etag; ``get`` honours ``If-None-Match`` the way
    the real store does (304 → ``not_modified``), so the store's
    revalidation logic is exercised for real.
    """

    def __init__(self):
        self.blobs: dict[str, dict] = {}
        self.puts = 0
        self.gets = 0
        #: Downloads that actually transferred bytes (a 200, not a 304/404).
        self.transfers = 0

    def url_for(self, pathname):
        return f"https://fake.blob/{pathname}"

    def put(self, pathname, data):
        self.puts += 1
        etag = f'"v{self.puts}"'
        self.blobs[pathname] = {
            "url": self.url_for(pathname),
            "pathname": pathname,
            "data": data,
            "etag": etag,
            "uploadedAt": datetime.now(timezone.utc).isoformat(),
        }
        return BlobPutResult(url=self.url_for(pathname), etag=etag)

    def get(self, pathname, if_none_match=None):
        self.gets += 1
        record = self.blobs.get(pathname)
        if record is None:
            return None
        if if_none_match and if_none_match == record["etag"]:
            return BlobObject(data=None, etag=if_none_match, not_modified=True)
        self.transfers += 1
        return BlobObject(data=record["data"], etag=record["etag"])

    def delete(self, urls):
        for pathname, record in list(self.blobs.items()):
            if record["url"] in urls:
                del self.blobs[pathname]

    def list(self, prefix):
        return [
            {k: v for k, v in r.items() if k != "data"}
            for p, r in self.blobs.items()
            if p.startswith(prefix)
        ]


def _make_sqlite(path: str, marker: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE marker (value TEXT)")
    conn.execute("INSERT INTO marker VALUES (?)", (marker,))
    conn.commit()
    conn.close()


def _read_marker(path: str) -> str:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT value FROM marker").fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def user_dir(tmp_path, monkeypatch):
    """Isolate every path the store resolves under a throwaway directory.

    Some suites assign ``AppConfig._base_user_dir`` directly and can leave
    the override pointing at their own tmp dir; clearing it makes the env
    var authoritative again for this test.
    """
    monkeypatch.setenv("FAD_USER_DIR", str(tmp_path))
    monkeypatch.setattr(AppConfig(), "_base_user_dir_override", None)
    AppConfig._forced_mode = None
    yield tmp_path
    database.reset_engines()
    AppConfig._forced_mode = None


@pytest.fixture
def template(user_dir):
    """A pristine template file new sandboxes are cloned from."""
    path = DemoSessionStore.template_path()
    _make_sqlite(path, "template")
    return path


class TestSessionIdParsing:
    """Tests for validating the client-supplied sandbox id."""

    @pytest.mark.parametrize(
        "value",
        [
            "0123456789abcdef",
            "8f3c2d1e-4b5a-4c6d-9e7f-0a1b2c3d4e5f",
            "8f3c2d1e4b5a4c6d9e7f0a1b2c3d4e5f",
            "  visitor_0123456789ab  ",
        ],
    )
    def test_accepts_path_safe_ids(self, value):
        """Verify UUID-shaped ids (with or without dashes) are accepted."""
        assert parse_session_id(value) == value.strip()

    @pytest.mark.parametrize(
        "value",
        [None, "", "short", "../../etc/passwd", "has space 0123456789", "a" * 65, "x/y0123456789abcdef"],
    )
    def test_rejects_unsafe_ids(self, value):
        """Verify anything that could escape the sessions directory is dropped."""
        assert parse_session_id(value) is None


class TestPathResolution:
    """Tests for how a bound sandbox id changes the demo paths."""

    def test_session_nests_under_demo_env(self, user_dir):
        """Verify a bound id resolves to ``demo_env/sessions/<id>/demo_data.db``."""
        path = DemoSessionStore.local_db_path(SID_A)
        assert path == str(user_dir / "demo_env" / "sessions" / SID_A / "demo_data.db")

    def test_unbound_context_keeps_shared_path(self, user_dir):
        """Verify the shared demo DB path is unchanged when no id is bound."""
        config = AppConfig()
        token = config.set_demo_mode(True, ensure_dir=False)
        try:
            assert config.get_db_path() == str(user_dir / "demo_env" / "demo_data.db")
        finally:
            config.reset_demo_mode(token)

    def test_session_id_never_leaks_into_real_mode(self, user_dir):
        """Verify a bound id is ignored outside demo mode."""
        config = AppConfig()
        token = config.set_demo_session(SID_A)
        try:
            assert config.get_db_path() == str(user_dir / "data.db")
        finally:
            config.reset_demo_session(token)


class TestEnsureLocal:
    """Tests for materializing a sandbox on the serving instance."""

    def test_restores_from_blob_when_present(self, user_dir, template):
        """Verify a persisted sandbox wins over the template."""
        backend = FakeBlobBackend()
        _make_sqlite(str(user_dir / "src.db"), "from-blob")
        backend.put(blob_pathname(SID_A), (user_dir / "src.db").read_bytes())
        store = DemoSessionStore(backend)

        store.ensure_local(SID_A)

        assert _read_marker(store.local_db_path(SID_A)) == "from-blob"

    def test_clones_template_when_nothing_persisted(self, user_dir, template):
        """Verify a new visitor starts from the pristine template."""
        store = DemoSessionStore(FakeBlobBackend())

        store.ensure_local(SID_A)

        assert _read_marker(store.local_db_path(SID_A)) == "template"

    def test_clones_template_without_backend(self, user_dir, template):
        """Verify sandboxes still isolate visitors when Blob is not configured."""
        store = DemoSessionStore(None)

        store.ensure_local(SID_A)
        store.ensure_local(SID_B)

        assert store.local_db_path(SID_A) != store.local_db_path(SID_B)
        assert os.path.exists(store.local_db_path(SID_B))

    def test_builds_from_snapshot_without_template(self, user_dir):
        """Verify the frozen demo snapshot is used when no template exists.

        Local dev and tests never call ``snapshot_template``; the store must
        then build the demo DB straight into the sandbox directory.
        """
        store = DemoSessionStore(None)

        store.ensure_local(SID_A)

        path = store.local_db_path(SID_A)
        conn = sqlite3.connect(path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM bank_transactions").fetchone()[0]
        finally:
            conn.close()
        assert count > 0
        assert not os.path.exists(user_dir / "demo_env" / "demo_data.db")

    def test_is_idempotent(self, user_dir, template):
        """Verify a second call leaves an existing sandbox untouched."""
        store = DemoSessionStore(FakeBlobBackend())
        store.ensure_local(SID_A)
        path = store.local_db_path(SID_A)
        conn = sqlite3.connect(path)
        conn.execute("UPDATE marker SET value = 'edited'")
        conn.commit()
        conn.close()

        store.ensure_local(SID_A)

        assert _read_marker(path) == "edited"


class TestSync:
    """Tests for per-request revalidation against the persisted copy.

    A serverless page load fans out over several instances; these tests
    play two instances as two stores sharing one backend.
    """

    def _edit(self, path: str, value: str) -> None:
        conn = sqlite3.connect(path)
        conn.execute("UPDATE marker SET value = ?", (value,))
        conn.commit()
        conn.close()

    def test_other_instance_sees_a_write_after_persist(self, user_dir, template, monkeypatch):
        """Verify instance B replaces its local copy once A has persisted a newer one."""
        backend = FakeBlobBackend()
        a, b = DemoSessionStore(backend), DemoSessionStore(backend)
        a.sync(SID_A)
        b_dir = user_dir / "b"
        # Give B its own "/tmp" by resolving its paths under another user dir.
        monkeypatch.setenv("FAD_USER_DIR", str(b_dir))
        b_template = DemoSessionStore.template_path()
        _make_sqlite(b_template, "template")
        b.sync(SID_A)
        assert _read_marker(b.local_db_path(SID_A)) == "template"
        monkeypatch.setenv("FAD_USER_DIR", str(user_dir))

        self._edit(a.local_db_path(SID_A), "written-on-a")
        assert a.persist(SID_A) is True

        monkeypatch.setenv("FAD_USER_DIR", str(b_dir))
        b._checked_at.clear()
        b.sync(SID_A)
        assert _read_marker(b.local_db_path(SID_A)) == "written-on-a"

    def test_not_modified_keeps_local_file(self, user_dir, template):
        """Verify a 304 leaves the local file (and its read-time writes) alone."""
        backend = FakeBlobBackend()
        store = DemoSessionStore(backend)
        store.sync(SID_A)
        store.persist(SID_A)
        self._edit(store.local_db_path(SID_A), "local-derived-rows")
        store._checked_at.clear()

        store.sync(SID_A)

        assert _read_marker(store.local_db_path(SID_A)) == "local-derived-rows"
        assert backend.gets == 2

    def test_burst_shares_one_revalidation(self, user_dir, template):
        """Verify a dozen near-simultaneous requests cost one download check."""
        backend = FakeBlobBackend()
        store = DemoSessionStore(backend)
        store.sync(SID_A)
        store.persist(SID_A)
        store._checked_at.clear()

        for _ in range(12):
            store.sync(SID_A)

        assert backend.gets == 2

    def test_revalidation_failure_serves_local_copy(self, user_dir, template):
        """Verify a Blob outage degrades to the local copy, never a 500."""

        class Flaky(FakeBlobBackend):
            def get(self, pathname, if_none_match=None):
                raise RuntimeError("blob down")

        store = DemoSessionStore(Flaky())

        store.sync(SID_A)

        assert _read_marker(store.local_db_path(SID_A)) == "template"

    def test_persist_records_etag_so_next_sync_is_a_304(self, user_dir, template):
        """Verify the uploading instance does not re-download its own write."""
        backend = FakeBlobBackend()
        store = DemoSessionStore(backend)
        store.sync(SID_A)
        self._edit(store.local_db_path(SID_A), "mine")
        store.persist(SID_A)
        store._checked_at.clear()

        transfers_before = backend.transfers

        store.sync(SID_A)

        assert _read_marker(store.local_db_path(SID_A)) == "mine"
        assert store._etags[SID_A] == backend.blobs[blob_pathname(SID_A)]["etag"]
        # The revalidation happened (the window was cleared) but answered 304.
        assert backend.gets == 2
        assert backend.transfers == transfers_before


    def test_corrupt_download_does_not_clobber_the_local_copy(self, user_dir, template):
        """Verify a payload that is not a SQLite file leaves the sandbox alone.

        The whole database is the unit of persistence, so a truncated upload
        or an error page served with a 200 would otherwise be written over a
        working sandbox and turn every query into "no such table" — with a
        manual reset the visitor's only way out.
        """
        backend = FakeBlobBackend()
        store = DemoSessionStore(backend)
        store.sync(SID_A)
        self._edit(store.local_db_path(SID_A), "still-good")
        backend.put(blob_pathname(SID_A), b"<html>Attention Required</html>")
        store._checked_at.clear()

        store.sync(SID_A)

        assert _read_marker(store.local_db_path(SID_A)) == "still-good"
        # No etag recorded, so a repaired blob is picked up on the next check.
        assert store._etags.get(SID_A) is None

    def test_corrupt_download_still_seeds_a_missing_sandbox(self, user_dir, template):
        """Verify a visitor with no local copy gets a fresh one, not a broken file."""
        backend = FakeBlobBackend()
        backend.put(blob_pathname(SID_A), b"")
        store = DemoSessionStore(backend)

        store.sync(SID_A)

        assert _read_marker(store.local_db_path(SID_A)) == "template"


class TestPersist:
    """Tests for mirroring a sandbox to the backend."""

    def test_uploads_current_file_bytes(self, user_dir, template):
        """Verify persist ships the sandbox file under its blob pathname."""
        backend = FakeBlobBackend()
        store = DemoSessionStore(backend)
        store.ensure_local(SID_A)

        assert store.persist(SID_A) is True

        with open(store.local_db_path(SID_A), "rb") as fh:
            assert backend.blobs[blob_pathname(SID_A)]["data"] == fh.read()

    def test_noop_without_backend_or_file(self, user_dir, template):
        """Verify persist is a no-op when there is nowhere or nothing to upload."""
        assert DemoSessionStore(None).persist(SID_A) is False
        assert DemoSessionStore(FakeBlobBackend()).persist(SID_A) is False

    def test_upload_failure_is_swallowed(self, user_dir, template):
        """Verify a failed upload never propagates into the user's request."""

        class BrokenBackend(FakeBlobBackend):
            def put(self, pathname, data):
                raise RuntimeError("quota")

        store = DemoSessionStore(BrokenBackend())
        store.ensure_local(SID_A)

        assert store.persist(SID_A) is False


class TestReset:
    """Tests for discarding a sandbox."""

    def test_reseeds_locally_and_deletes_remote(self, user_dir, template):
        """Verify reset wipes the visitor's edits everywhere and re-clones."""
        backend = FakeBlobBackend()
        store = DemoSessionStore(backend)
        store.ensure_local(SID_A)
        path = store.local_db_path(SID_A)
        conn = sqlite3.connect(path)
        conn.execute("UPDATE marker SET value = 'edited'")
        conn.commit()
        conn.close()
        store.persist(SID_A)
        assert blob_pathname(SID_A) in backend.blobs

        store.reset(SID_A)

        assert _read_marker(path) == "template"
        assert blob_pathname(SID_A) not in backend.blobs

    def test_leaves_other_sandboxes_alone(self, user_dir, template):
        """Verify one visitor's reset cannot touch another visitor's copy."""
        backend = FakeBlobBackend()
        store = DemoSessionStore(backend)
        for sid in (SID_A, SID_B):
            store.ensure_local(sid)
            store.persist(sid)
        conn = sqlite3.connect(store.local_db_path(SID_B))
        conn.execute("UPDATE marker SET value = 'b-edit'")
        conn.commit()
        conn.close()

        store.reset(SID_A)

        assert _read_marker(store.local_db_path(SID_B)) == "b-edit"
        assert blob_pathname(SID_B) in backend.blobs


class TestPrune:
    """Tests for expiring stale persisted sandboxes."""

    def test_deletes_only_blobs_older_than_ttl(self, user_dir, monkeypatch):
        """Verify pruning respects the TTL and the sandbox prefix."""
        backend = FakeBlobBackend()
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        backend.blobs[blob_pathname("old")] = {
            "url": "https://fake.blob/old",
            "pathname": blob_pathname("old"),
            "data": b"",
            "uploadedAt": old,
        }
        backend.blobs[blob_pathname("fresh")] = {
            "url": "https://fake.blob/fresh",
            "pathname": blob_pathname("fresh"),
            "data": b"",
            "uploadedAt": datetime.now(timezone.utc).isoformat(),
        }
        backend.blobs["unrelated/old.bin"] = {
            "url": "https://fake.blob/unrelated",
            "pathname": "unrelated/old.bin",
            "data": b"",
            "uploadedAt": old,
        }
        monkeypatch.setenv(demo_sessions.TTL_ENV, "14")

        deleted = DemoSessionStore(backend).prune()

        assert deleted == 1
        assert set(backend.blobs) == {blob_pathname("fresh"), "unrelated/old.bin"}

    def test_zero_without_backend(self, user_dir):
        """Verify pruning is a no-op when Blob is not configured."""
        assert DemoSessionStore(None).prune() == 0


class TestSnapshotTemplate:
    """Tests for freezing the shared demo DB as the sandbox template."""

    def test_copies_shared_demo_db(self, user_dir):
        """Verify the template is a byte copy of the shared demo database."""
        shared = str(user_dir / "demo_env" / "demo_data.db")
        _make_sqlite(shared, "shared")

        demo_sessions.snapshot_template()

        assert _read_marker(DemoSessionStore.template_path()) == "shared"

    def test_noop_when_shared_db_missing(self, user_dir):
        """Verify a missing shared DB does not raise or create a template."""
        demo_sessions.snapshot_template()
        assert not os.path.exists(DemoSessionStore.template_path())


class TestNonDurableMode:
    """Tests for the documented no-``BLOB_READ_WRITE_TOKEN`` deployment."""

    @pytest.fixture(autouse=True)
    def _clear_process_store(self):
        """Drop the memoized process-wide store around each test."""
        demo_sessions.set_store(None)
        yield
        demo_sessions.set_store(None)

    def test_store_is_not_durable_without_a_token(self, user_dir, monkeypatch):
        """Verify a deployment with no Blob store reports itself non-durable.

        ``blob_configured`` in ``demo_mode_status`` and the cold-start
        warning in ``index.py`` both read this flag, so it is what makes a
        missing Blob store visible instead of silent.
        """
        monkeypatch.delenv(vercel_blob.TOKEN_ENV, raising=False)

        assert demo_sessions.get_store().durable is False

    def test_store_is_durable_with_a_token(self, user_dir, monkeypatch):
        """Verify a configured token produces a store that claims durability."""
        monkeypatch.setenv(vercel_blob.TOKEN_ENV, "vercel_blob_rw_store123_secret")

        store = demo_sessions.get_store()

        assert store.durable is True
        assert store.backend.store_id == "store123"

    def test_store_is_built_once_per_process(self, user_dir, monkeypatch):
        """Verify the store is memoized rather than rebuilt per request."""
        monkeypatch.delenv(vercel_blob.TOKEN_ENV, raising=False)

        first = demo_sessions.get_store()
        monkeypatch.setenv(vercel_blob.TOKEN_ENV, "vercel_blob_rw_store123_secret")

        assert demo_sessions.get_store() is first

    def test_reset_reseeds_without_a_backend(self, user_dir, template):
        """Verify "Reset demo data" works on a deployment with no Blob store."""
        store = DemoSessionStore(None)
        store.ensure_local(SID_A)
        conn = sqlite3.connect(store.local_db_path(SID_A))
        conn.execute("UPDATE marker SET value = 'edited'")
        conn.commit()
        conn.close()

        store.reset(SID_A)

        assert _read_marker(store.local_db_path(SID_A)) == "template"
