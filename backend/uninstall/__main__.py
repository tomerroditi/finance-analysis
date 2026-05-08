"""Entry point for ``python -m backend.uninstall``."""

import sys

from backend.uninstall.cleanup import cli

if __name__ == "__main__":
    sys.exit(cli())
