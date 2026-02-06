import datetime
import os
import sys

from sqlalchemy import text

# Add current directory to path
sys.path.append(os.getcwd())

from backend.database import get_db_context
from backend.repositories.transactions_repository import TransactionsRepository
from backend.scraper.scrapers import DummyRegularScraper
from backend.services.tagging_rules_service import TaggingRulesService


def test_auto_tagging():
    print("Setting up test...")
    with get_db_context() as db:
        # 1. Create a dummy rule
        tagging_service = TaggingRulesService(db)
        rule_name = "AutoTag Test Rule"

        # Clean up existing test rule if any
        existing_rules = tagging_service.get_all_rules()
        if not existing_rules.empty:
            for _, rule in existing_rules.iterrows():
                if rule["name"] == rule_name:
                    tagging_service.delete_rule(rule["id"])

        print("Creating tagging rule...")
        tagging_service.add_rule(
            name=rule_name,
            conditions={
                "type": "CONDITION",
                "field": "description",
                "operator": "contains",
                "value": "Test Transaction AutoTag",
            },
            category="TestCategory",
            tag="TestTag",
        )
        db.commit()

        # 2. Run Dummy Scraper
        # We need to mock the `_scrape_data` method of DummyRegularScraper because it normally spawns a node process.
        # However, looking at the code, DummyRegularScraper might not need node if we subclass and override `scrape_data`.

    class MockScraper(DummyRegularScraper):
        def scrape_data(self, start_date):
            # Simulate finding data
            import pandas as pd

            self.data = pd.DataFrame(
                [
                    {
                        "date": datetime.date.today().isoformat(),
                        "desc": "Test Transaction AutoTag",
                        "amount": -100.0,
                        "charged_amount": -100.0,
                        "id": "999999999",  # Dummy ID
                    }
                ]
            )

    print("Running scraper...")
    # Initialize scraper
    scraper = MockScraper(
        account_name="Test Account",
        credentials={},
        start_date=datetime.date.today(),
        process_id=999,
    )

    # Run the logic (pull_data_to_db calls _apply_auto_tagging)
    scraper.pull_data_to_db()

    # 3. Verify
    print("Verifying results...")
    with get_db_context() as db:
        repo = TransactionsRepository(db)
        # Get the transaction
        query = "SELECT * FROM bank_transactions WHERE id = '999999999'"
        df = repo.get_table(query=query)

        if df.empty:
            print("❌ Test Failed: Transaction not found in DB.")
            return

        row = df.iloc[0]
        # print(f"Transaction Unique ID: {row['unique_id']}")
        # print(f"Transaction Desc: '{row['desc']}'")
        # print(f"Transaction Category: {row['category']}")
        # print(f"Transaction Tag: {row['tag']}")

        if row["category"] == "TestCategory" and row["tag"] == "TestTag":
            print("✅ Test Passed: Transaction was auto-tagged.")
        else:
            print("❌ Test Failed: Transaction was NOT auto-tagged.")

        # Cleanup
        print("Cleaning up...")
        db.execute(text("DELETE FROM bank_transactions WHERE id = '999999999'"))

        # Delete rule
        existing_rules = tagging_service.get_all_rules()
        for _, rule in existing_rules.iterrows():
            if rule["name"] == rule_name:
                tagging_service.delete_rule(rule["id"])
        db.commit()


if __name__ == "__main__":
    test_auto_tagging()
