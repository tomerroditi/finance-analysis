import { CompanyTypes, createScraper } from 'israeli-bank-scrapers';

// get the id, card6Digits and password from the command line
const args = process.argv.slice(2);
const id = args[0];
const card6Digits = args[1];
const password = args[2];
const start_date = args[3];


(async function() {
  try {
    // read documentation below for available options
    const options = {
      companyId: CompanyTypes.isracard,
      startDate: new Date(start_date),
      combineInstallments: false,
      showBrowser: false
    };

    // read documentation below for information about credentials
    const credentials = {
      id: id,
      card6Digits: card6Digits,
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
      throw new Error(`${scrapeResult.errorType}: ${scrapeResult.errorMessage}`);
    }
  } catch(e) {
    console.error(`logging error: ${e.message}`);
  }
})();