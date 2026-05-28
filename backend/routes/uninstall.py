"""macOS-only in-app uninstall route.

Triggered by Settings → Advanced → Uninstall…. Removes Keychain entries
synchronously (those don't require killing the process), then writes a
small deferred shell script that — after this response has flushed —
removes the .app bundle from /Applications, the synced runtime copy at
``~/.finance-analysis/app``, optionally the rest of the user-data dir,
and finally kills the uvicorn parent process.

The deferred script trick is necessary because a running .app cannot
delete its own bundle — macOS holds an open handle on the executable
for as long as the process is alive. Spawning a Terminal window that
runs the script after a small delay both decouples the cleanup from
this HTTP handler and gives the user a visible record of what happened.

Windows is intentionally not supported here: Windows uninstalls happen
through Add/Remove Programs (NSIS Uninstall.exe), which already calls
the same ``backend.uninstall.cleanup`` module via
``python -m backend.uninstall``. Adding an in-app path on Windows
would invite users to remove the venv that's currently executing the
request.
"""

from __future__ import annotations

import logging
import os
import shlex
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.config import AppConfig
from backend.uninstall.cleanup import run as run_cleanup

router = APIRouter()
logger = logging.getLogger(__name__)


class UninstallRequest(BaseModel):
    wipe_data: bool = False


class UninstallResponse(BaseModel):
    status: str
    keyring_entries_deleted: int
    user_dir_will_be_removed: bool


_DEFERRED_SCRIPT = r"""#!/bin/bash
set -u

APP_NAME="Finance Analysis"
APP_BUNDLE="/Applications/${APP_NAME}.app"
USER_DIR="__USER_DIR__"
USER_APP="${USER_DIR}/app"
WIPE_DATA="__WIPE_DATA__"
PARENT_PID="__PARENT_PID__"

# Wait for the HTTP response to flush back to the browser.
sleep 2

echo "Removing ${APP_NAME}..."

# Stop the running backend; ignore failure if it already exited.
if [ -n "${PARENT_PID}" ]; then
    kill "${PARENT_PID}" 2>/dev/null || true
fi
pkill -f "uvicorn backend.main:app" 2>/dev/null || true

# Remove the .app bundle (if present).
if [ -d "${APP_BUNDLE}" ]; then
    rm -rf "${APP_BUNDLE}"
    echo "Removed ${APP_BUNDLE}"
fi

# Remove the synced runtime copy.
if [ -d "${USER_APP}" ]; then
    rm -rf "${USER_APP}"
    echo "Removed ${USER_APP}"
fi

# When wiping data, remove the entire user-data dir as a backstop —
# the cleanup module already attempted this, but if it failed (e.g.
# the DB file was open by this very process) doing it after we've
# killed the parent succeeds.
if [ "${WIPE_DATA}" = "1" ] && [ -d "${USER_DIR}" ]; then
    rm -rf "${USER_DIR}"
    echo "Removed ${USER_DIR}"
fi

echo ""
echo "${APP_NAME} has been uninstalled."
echo "You can close this Terminal window."
"""


def _write_deferred_script(*, wipe_data: bool, user_dir: str) -> Path:
    """Materialise the deferred-cleanup script under /tmp.

    Lives under ``/tmp`` because the user-data dir might be the thing
    we're about to delete. ``mkstemp`` + ``chmod 700`` keeps the script
    readable only by the current user (it doesn't contain secrets, but
    we'd rather not advertise the parent PID to other accounts on the
    machine).
    """
    parent_pid = os.getppid() or os.getpid()
    body = (
        _DEFERRED_SCRIPT
        .replace("__USER_DIR__", user_dir)
        .replace("__WIPE_DATA__", "1" if wipe_data else "0")
        .replace("__PARENT_PID__", str(parent_pid))
    )
    fd, path_str = tempfile.mkstemp(prefix="finance-analysis-uninstall-", suffix=".sh")
    with os.fdopen(fd, "w") as fh:
        fh.write(body)
    path = Path(path_str)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    return path


def _launch_in_terminal(script_path: Path) -> None:
    """Open Terminal.app and run the deferred script.

    ``osascript`` is the supported cross-architecture way to ask
    Terminal to open a new window with a command. The window stays
    open after the script exits so the user can read the summary.

    The path is escaped for both the AppleScript string literal and the
    shell ``bash`` invocation. ``mkstemp`` only produces safe paths today,
    but quoting here keeps a hostile/unexpected path from breaking out of
    the ``do script "..."`` literal into arbitrary command execution.
    """
    # Shell-quote for the bash invocation, then escape the result for the
    # AppleScript double-quoted string literal (\ and ").
    sh_quoted = shlex.quote(str(script_path))
    sh_quoted_for_as = sh_quoted.replace("\\", "\\\\").replace('"', '\\"')
    apple_script = (
        'tell application "Terminal"\n'
        "    activate\n"
        f'    do script "bash {sh_quoted_for_as}"\n'
        "end tell"
    )
    subprocess.Popen(["osascript", "-e", apple_script])


@router.post("", response_model=UninstallResponse)
def uninstall(req: UninstallRequest) -> UninstallResponse:
    """Run cleanup, schedule .app deletion, and shut the backend down."""
    if sys.platform != "darwin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="In-app uninstall is supported on macOS only.",
        )

    base = Path(AppConfig()._base_user_dir).expanduser()  # noqa: SLF001
    report = run_cleanup(wipe_data=req.wipe_data)
    logger.info("Uninstall cleanup report: %s", report.as_dict())

    script_path = _write_deferred_script(wipe_data=req.wipe_data, user_dir=str(base))
    _launch_in_terminal(script_path)

    return UninstallResponse(
        status="scheduled",
        keyring_entries_deleted=report.keyring_entries_deleted,
        user_dir_will_be_removed=req.wipe_data,
    )
