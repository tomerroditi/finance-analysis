"""
Centralized configuration management for the Finance Analysis backend.
Handles environment switching between production and demo modes.
"""

import os
from contextvars import ContextVar, Token

#: Per-request demo-mode flag. Context-local so two clients on one backend
#: can read different databases in the same process. Set by the
#: ``resolve_demo_mode`` middleware in ``backend/main.py`` from the
#: ``X-FAD-Demo`` header; defaults to real mode everywhere else (startup,
#: scripts, background work that has not explicitly opted in).
_demo_mode_ctx: ContextVar[bool] = ContextVar("fad_demo_mode", default=False)

#: Per-request demo *sandbox* id. Only meaningful in demo mode: when bound,
#: every demo path resolves under ``demo_env/sessions/<id>/`` so each
#: visitor of the shared Vercel deployment gets a private copy of the demo
#: database. ``None`` (the default everywhere else) means the single shared
#: demo database. Set by :mod:`backend.demo_sessions` from the
#: ``X-FAD-Demo-Session`` header.
_demo_session_ctx: ContextVar[str | None] = ContextVar(
    "fad_demo_session", default=None
)


class AppConfig:
    """Singleton configuration manager for the Finance Analysis backend.

    Provides a single shared instance (via ``__new__``) that controls whether
    the application runs in production or demo mode. In demo mode all paths
    point to an isolated ``demo_env/`` subdirectory so demo data never touches
    production data. Paths can also be overridden via environment variables
    (``FAD_USER_DIR``, ``FAD_DB_PATH``, ``FAD_CREDENTIALS_PATH``, etc.).
    """

    _instance = None

    #: Process-wide pin that overrides both the contextvar and the request
    #: header. ``None`` means "defer to context". Set to ``True`` by the
    #: Vercel entry point (``index.py``), where the whole deployment is a
    #: shared demo instance and no client may opt out.
    _forced_mode: bool | None = None

    #: Base user directory override. ``None`` means "resolve from
    #: ``FAD_USER_DIR`` / the home directory at call time". Lives on the
    #: singleton *instance* (initialised in ``__new__``), never on the class:
    #: the ``_base_user_dir`` setter always wrote the instance slot, so a
    #: class-level default let callers save the class attribute, assign the
    #: instance one, and "restore" a value that never changed.
    _base_user_dir_override: str | None

    def __new__(cls):
        """Return the shared singleton instance, creating it on first call."""
        if cls._instance is None:
            cls._instance = super(AppConfig, cls).__new__(cls)
            cls._instance._base_user_dir_override = None
        return cls._instance

    @property
    def is_demo_mode(self) -> bool:
        """Return ``True`` when the current context is in demo mode.

        Resolution order: the process-wide ``_forced_mode`` pin, then the
        context-local flag set from the request header.
        """
        if self._forced_mode is not None:
            return self._forced_mode
        return _demo_mode_ctx.get()

    def set_demo_mode(self, enabled: bool, *, ensure_dir: bool = True) -> Token[bool]:
        """Set demo mode for the current context.

        When enabling, the demo user directory is created if it does not
        exist (unless ``ensure_dir`` is ``False``).

        Parameters
        ----------
        enabled : bool
            ``True`` to switch this context to the isolated demo
            environment, ``False`` for production.
        ensure_dir : bool
            Whether to ``os.makedirs`` the demo user directory when
            enabling. Defaults to ``True`` for callers that need the
            directory to exist (the demo-database lifecycle: preparing,
            resetting, or checking demo_mode_status against a freshly
            created install). Pass ``False`` for hot paths that merely
            bind the flag for the duration of a request and never touch
            the filesystem themselves — e.g. the ``resolve_demo_mode``
            middleware, which otherwise pays a blocking ``os.makedirs``
            syscall on the event loop for every single demo-mode request.
        Returns
        -------
        Token[bool]
            Token for :meth:`reset_demo_mode`. Callers that set the flag for
            a bounded scope (a request, a scrape) must reset it, or a pooled
            worker thread will carry the mode into unrelated work.
        """
        token = _demo_mode_ctx.set(enabled)
        if enabled and ensure_dir:
            os.makedirs(self.get_user_dir(), exist_ok=True)
        return token

    def reset_demo_mode(self, token: Token[bool]) -> None:
        """Restore the demo flag to its value before ``token`` was issued.

        Parameters
        ----------
        token : Token[bool]
            The token returned by :meth:`set_demo_mode`.
        """
        _demo_mode_ctx.reset(token)

    def get_demo_session(self) -> str | None:
        """Return the demo sandbox id bound to the current context, if any."""
        return _demo_session_ctx.get()

    def set_demo_session(self, session_id: str | None) -> Token[str | None]:
        """Bind a demo sandbox id for the current context.

        Parameters
        ----------
        session_id : str | None
            Sandbox id (already validated by the caller), or ``None`` to
            address the shared demo database.

        Returns
        -------
        Token[str | None]
            Token for :meth:`reset_demo_session`; bounded scopes must reset.
        """
        return _demo_session_ctx.set(session_id)

    def reset_demo_session(self, token: Token[str | None]) -> None:
        """Restore the sandbox id to its value before ``token`` was issued.

        Parameters
        ----------
        token : Token[str | None]
            The token returned by :meth:`set_demo_session`.
        """
        _demo_session_ctx.reset(token)

    @property
    def _base_user_dir(self) -> str:
        """Base user directory, resolving ``FAD_USER_DIR`` at call time.

        Previously this was read once at class-definition time, so any
        caller that set the env var after importing the module silently got
        the wrong directory.
        """
        if self._base_user_dir_override is not None:
            return self._base_user_dir_override
        return os.environ.get(
            "FAD_USER_DIR",
            os.path.join(os.path.expanduser("~"), ".finance-analysis"),
        )

    @_base_user_dir.setter
    def _base_user_dir(self, value: str | None) -> None:
        """Pin (or, with ``None``, un-pin) the base user directory.

        Assign a directory to route every path this config produces under
        it; assign ``None`` to go back to resolving ``FAD_USER_DIR`` at call
        time. Callers that want to restore a previous state must save and
        restore ``_base_user_dir_override`` — saving the resolved
        ``_base_user_dir`` and assigning it back pins the singleton to a
        concrete path, after which ``FAD_USER_DIR`` is silently ignored.
        """
        self._base_user_dir_override = value

    def get_demo_root_dir(self) -> str:
        """Return the shared demo directory, ignoring any bound sandbox id."""
        return os.path.join(self._base_user_dir, "demo_env")

    def get_user_dir(self) -> str:
        """Get the current user directory based on mode.

        In demo mode a bound sandbox id nests the directory one level deeper
        (``demo_env/sessions/<id>``) so per-visitor sandboxes never share a
        database file with each other or with the shared demo copy.
        """
        if self.is_demo_mode:
            demo_root = self.get_demo_root_dir()
            session_id = _demo_session_ctx.get()
            if session_id is not None:
                return os.path.join(demo_root, "sessions", session_id)
            return demo_root
        return self._base_user_dir

    def get_db_path(self) -> str:
        """Get the current database path."""
        # Allow override via env var in non-demo mode only
        if not self.is_demo_mode and os.environ.get("FAD_DB_PATH"):
            return os.environ.get("FAD_DB_PATH")

        filename = "demo_data.db" if self.is_demo_mode else "data.db"
        return os.path.join(self.get_user_dir(), filename)

    def get_credentials_path(self) -> str:
        """Get the current credentials file path."""
        if not self.is_demo_mode and os.environ.get("FAD_CREDENTIALS_PATH"):
            return os.environ.get("FAD_CREDENTIALS_PATH")

        return os.path.join(self.get_user_dir(), "credentials.yaml")

    def get_categories_path(self) -> str:
        """Get the current categories file path."""
        if not self.is_demo_mode and os.environ.get("FAD_CATEGORIES_PATH"):
            return os.environ.get("FAD_CATEGORIES_PATH")

        return os.path.join(self.get_user_dir(), "categories.yaml")

    def get_categories_icons_path(self) -> str:
        """Get the current categories icons file path."""
        if not self.is_demo_mode and os.environ.get("FAD_CATEGORIES_ICONS_PATH"):
            return os.environ.get("FAD_CATEGORIES_ICONS_PATH")

        return os.path.join(self.get_user_dir(), "categories_icons.yaml")
