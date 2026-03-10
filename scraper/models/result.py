from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from scraper.models.account import AccountResult


class LoginResult(str, Enum):
    SUCCESS = "success"
    INVALID_PASSWORD = "invalid_password"
    CHANGE_PASSWORD = "change_password"
    ACCOUNT_BLOCKED = "account_blocked"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ScrapingResult:
    """Result of a complete scraping operation."""
    success: bool
    accounts: list[AccountResult] = field(default_factory=list)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
