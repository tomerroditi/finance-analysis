"""Static-quality gate for the backend package.

Runs ruff against ``backend/`` with the configuration in ``pyproject.toml``
(``[tool.ruff]``). That configuration enables the annotation (``ANN``) and
NumPy-docstring (``D``) rule families, so this is what keeps every backend
function typed and documented: a new untyped parameter, a missing return
annotation or an undocumented public function fails the backend suite locally
and in CI, not in review.

Fix a failure with ``poetry run ruff check backend --fix`` (plus a manual pass
for what has no autofix) and ``poetry run ruff format backend``.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _ruff(*args: str) -> subprocess.CompletedProcess[str]:
    """Run ruff from the active interpreter's environment at the repo root."""
    return subprocess.run(
        [sys.executable, "-m", "ruff", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.xdist_group("ruff")
class TestBackendRuff:
    """The backend package passes ruff's lint rules and formatter."""

    def test_lint_is_clean(self) -> None:
        """``ruff check backend`` reports no violations."""
        result = _ruff("check", "backend", "--output-format", "concise")
        assert result.returncode == 0, result.stdout + result.stderr

    def test_formatting_is_clean(self) -> None:
        """``ruff format --check backend`` would reformat nothing."""
        result = _ruff("format", "--check", "backend")
        assert result.returncode == 0, result.stdout + result.stderr
