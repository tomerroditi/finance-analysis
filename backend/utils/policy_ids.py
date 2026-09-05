"""Backend access to the root-package policy-ID helpers.

The canonical implementation lives in ``scraper/utils/policy_ids.py`` — the
scraper is where a provider's raw policy ID is first seen, so it owns the
normalization, and re-exporting keeps the two sides from drifting.

It is loaded straight from its file rather than with ``import
scraper.utils.policy_ids`` for two reasons: the root ``scraper`` package
collides with ``backend.scraper`` (see ``backend/scraper/adapter.py``), and
``scraper/__init__.py`` transitively imports ``httpx`` and Playwright, which
this pure-string helper must not drag into the backend.
"""

import importlib.util
import os

_HELPER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scraper",
    "utils",
    "policy_ids.py",
)

_spec = importlib.util.spec_from_file_location("_fad_scraper_policy_ids", _HELPER_PATH)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

normalize_policy_id = _module.normalize_policy_id
policy_id_key = _module.policy_id_key

__all__ = ["normalize_policy_id", "policy_id_key"]
