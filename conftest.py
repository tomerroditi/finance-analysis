"""Root conftest — ensures the project root is on sys.path.

This is needed because the root ``scraper`` package has the same name as
``backend.scraper``, and without the project root on the path, Python's
import system cannot resolve the root package.
"""
import os
import sys

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
