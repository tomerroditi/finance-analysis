from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TransactionType(str, Enum):
    NORMAL = "normal"
    INSTALLMENTS = "installments"


class TransactionStatus(str, Enum):
    COMPLETED = "completed"
    PENDING = "pending"


@dataclass
class InstallmentInfo:
    """Installment payment details."""
    number: int
    total: int


@dataclass
class Transaction:
    """A single financial transaction scraped from a provider."""
    type: TransactionType
    status: TransactionStatus
    date: str
    processed_date: str
    original_amount: float
    original_currency: str
    charged_amount: float
    description: str
    identifier: Optional[str] = None
    charged_currency: Optional[str] = None
    memo: Optional[str] = None
    category: Optional[str] = None
    installments: Optional[InstallmentInfo] = None
