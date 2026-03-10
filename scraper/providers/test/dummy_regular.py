import asyncio
import random
from datetime import date, timedelta

from scraper.base import BaseScraper, ScraperOptions
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType

MERCHANTS = [
    "Supermarket",
    "Cinema",
    "Gas Station",
    "Electric Company",
    "Water Company",
    "Internet Provider",
    "Restaurant",
    "Pharmacy",
    "Clothing Store",
    "Electronics Store",
    "Coffee Shop",
    "Gym",
]


class DummyRegularScraper(BaseScraper):
    """Test scraper that generates fake transactions without real credentials.

    Useful for testing the scraping pipeline without needing a browser or
    actual bank credentials.
    """

    def __init__(
        self,
        provider: str,
        credentials: dict,
        options: ScraperOptions | None = None,
    ):
        super().__init__(provider, credentials, options)

    async def initialize(self) -> None:
        """No-op initialization for dummy scraper."""

    async def login(self) -> LoginResult:
        """Simulate login with a short delay.

        Returns
        -------
        LoginResult
            Always returns SUCCESS after a 1-second delay.
        """
        await asyncio.sleep(1)
        return LoginResult.SUCCESS

    async def fetch_data(self) -> list[AccountResult]:
        """Generate random fake transactions.

        Returns
        -------
        list[AccountResult]
            A single account with 3-13 random transactions.
        """
        num_transactions = random.randint(3, 13)
        today = date.today()
        start = self.options.start_date

        transactions = []
        for i in range(num_transactions):
            days_range = (today - start).days
            random_days = random.randint(0, max(days_range, 0))
            txn_date = start + timedelta(days=random_days)
            date_str = txn_date.isoformat()

            amount = round(random.uniform(-1000, -10), 2)
            merchant = random.choice(MERCHANTS)

            transactions.append(
                Transaction(
                    type=TransactionType.NORMAL,
                    status=TransactionStatus.COMPLETED,
                    date=date_str,
                    processed_date=date_str,
                    original_amount=amount,
                    original_currency="ILS",
                    charged_amount=amount,
                    description=merchant,
                    identifier=f"DEMO-{i}-{date_str}",
                )
            )

        total = round(sum(t.charged_amount for t in transactions), 2)
        account = AccountResult(
            account_number="DEMO-000000",
            transactions=transactions,
            balance=round(10000 + total, 2),
        )
        return [account]


class DummyCreditCardScraper(DummyRegularScraper):
    """Dummy credit card scraper for testing.

    Identical behavior to DummyRegularScraper; exists as a separate class
    for type distinction in the scraper registry.
    """
