"""Provider policy-ID helpers, re-exported for provider code.

The definition lives in ``backend/utils/policy_ids.py`` — see that module for
why the helpers sit on the backend side and what they guard against. Provider
code imports them from here so the scraper's own namespace still reads
naturally; ``backend.utils`` is a stdlib-only leaf, so this costs the scraper
no runtime dependency.
"""

from backend.utils.policy_ids import normalize_policy_id, policy_id_key

__all__ = ["normalize_policy_id", "policy_id_key"]
