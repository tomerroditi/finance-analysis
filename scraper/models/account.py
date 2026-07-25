from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from scraper.models.transaction import Transaction


class CardType(str, Enum):
    """Who issued a credit card — the bank or the credit-card company."""
    BANK_ISSUED = "bankIssued"
    COMPANY_ISSUED = "companyIssued"


@dataclass
class AccountResult:
    """Scraped data for a single account."""
    account_number: str
    transactions: list[Transaction] = field(default_factory=list)
    balance: Optional[float] = None
    balance_date: Optional[str] = None
    card_type: Optional[CardType] = None
    card_frame: Optional[float] = None
    savings_account: bool = False
    metadata: Optional[dict] = None
