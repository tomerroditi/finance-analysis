from dataclasses import dataclass, field
from typing import Optional

from scraper.models.transaction import Transaction


@dataclass
class AccountResult:
    """Scraped data for a single account."""
    account_number: str
    transactions: list[Transaction] = field(default_factory=list)
    balance: Optional[float] = None
