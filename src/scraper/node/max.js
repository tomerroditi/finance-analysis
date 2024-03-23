import { CompanyTypes, createScraper } from 'israeli-bank-scrapers';

// get the id, card6Digits and password from the command line
const args = process.argv.slice(2);
const username = args[0];
const password = args[1];
const start_date = args[2];

(async function() {
  try {
    // read documentation below for available options
    const options = {
      companyId: CompanyTypes.max,
      startDate: new Date(start_date),
      combineInstallments: false,
      showBrowser: true
    };

    // read documentation below for information about credentials
    const credentials = {
      username: username,
      password: password
    };

    const scraper = createScraper(options);
    const scrapeResult = await scraper.scrape(credentials);

    if (scrapeResult.success) {
      scrapeResult.accounts.forEach((account) => {
        console.log(`found ${account.txns.length} transactions for account number ${account.accountNumber}`);
        account.txns.forEach((txn) => {
          console.log(`account number: ${account.accountNumber}| type: ${txn.type}| id: ${txn.identifier}| date: ${txn.date}| amount: ${txn.chargedAmount}| desc: ${txn.description}| status: ${txn.status}`);
        });
      });
    }
    else {
      throw new Error(scrapeResult.errorType);
    }
  } catch(e) {
    console.error(`scraping failed for the following reason: ${e.message}`);
  }
})();