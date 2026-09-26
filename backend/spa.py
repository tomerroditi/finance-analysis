"""Serve the production frontend build from the API process."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.runtime import bundle_root, source_root


def resolve_frontend_dist() -> Path:
    """Locate the production frontend build.

    In a PyInstaller-frozen bundle the build lives under ``sys._MEIPASS``;
    everywhere else ``frontend/dist`` sits next to ``backend/`` in the source
    tree, which is also the fallback when a frozen bundle lacks one — so unit
    tests that import ``backend.main`` from a checkout work without any env
    var.

    Returns
    -------
    Path
        The ``frontend/dist`` directory to serve (it may not exist).
    """
    bundled = bundle_root() / "frontend" / "dist"
    if bundled.is_dir():
        return bundled
    return source_root() / "frontend" / "dist"


def mount_frontend(app: FastAPI) -> None:
    """Serve the SPA's assets and route non-API 404s to its ``index.html``.

    Does nothing when no frontend build is present (dev, where Vite serves
    it, and the test suite).

    Parameters
    ----------
    app : FastAPI
        Application to mount the frontend on.
    """
    frontend_dist = resolve_frontend_dist()
    if not frontend_dist.is_dir():
        return

    app.mount(
        "/assets",
        StaticFiles(directory=frontend_dist / "assets"),
        name="static-assets",
    )
    dist = frontend_dist.resolve()

    async def spa_fallback(request: Request, exc: Exception) -> Response:
        """Serve the React SPA for non-API 404s (client-side routing).

        Resolves the requested path and verifies it lives inside the frontend
        dist directory before serving to prevent path traversal (e.g.
        ``GET /../../etc/passwd``).

        Parameters
        ----------
        request : Request
            Request that matched no route.
        exc : Exception
            The 404 being handled.

        Returns
        -------
        Response
            A JSON 404 under ``/api/``, else the requested dist file or
            ``index.html``.
        """
        if request.url.path.startswith("/api/"):
            detail = getattr(exc, "detail", "Not found")
            return JSONResponse(status_code=404, content={"detail": detail})

        index_html = dist / "index.html"
        requested = request.url.path.lstrip("/")
        if not requested:
            return FileResponse(index_html)

        candidate = (dist / requested).resolve()
        try:
            candidate.relative_to(dist)
        except ValueError:
            return FileResponse(index_html)

        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_html)

    app.add_exception_handler(404, spa_fallback)
