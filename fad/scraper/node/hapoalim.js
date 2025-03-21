import { CompanyTypes, createScraper } from 'israeli-bank-scrapers';

// get the id, card6Digits and password from the command line
const args = process.argv.slice(2);
const userCode = args[0];
const password = args[1];
const start_date = args[2];


(async function() {
  try {
    // create the options object
    const options = {
      companyId: CompanyTypes.hapoalim,
      startDate: new Date(start_date),
      combineInstallments: false,
      showBrowser: false,
    };

    // create the credentials object
    const credentials = {
      userCode: userCode,
      password: password
    };

    // create the scraper object
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
    else {  // if the scraping failed
      throw new Error(`${scrapeResult.errorType}: ${scrapeResult.errorMessage}`);
    }
  } catch(e) {
    console.error(`logging error: ${e.message}`);
  }
})();