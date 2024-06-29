import { CompanyTypes, createScraper } from 'israeli-bank-scrapers';

// Get the credentials and other parameters from command line arguments
const args = process.argv.slice(2);
const email = args[0];
const password = args[1];
const otpLongTermToken = args[2];
const phoneNumber = args[3];
const start_date = args[4];

(async function() {
  try {
    // Define the scraper options
    const options = {
      companyId: CompanyTypes.oneZero,  // Adjust based on the specific bank
      startDate: new Date(start_date),
      combineInstallments: false,
      showBrowser: true
    };

    const scraper = createScraper(options);
    const credentials = {
      email: email,
      password: password,
      phoneNumber: phoneNumber,
      otpLongTermToken: otpLongTermToken
    };

    // Start scraping with the provided credentials
    const scrapeResult = await scraper.scrape(credentials);

    // TODO: fix this part to handle the scrape result
    if (scrapeResult.success) {
      scrapeResult.accounts.forEach((account) => {
        console.log(`found ${account.txns.length} transactions for account number ${account.accountNumber}`);
        account.txns.forEach((txn) => {
          console.log(`account number: ${account.accountNumber}| type: ${txn.type}| id: ${txn.identifier}| date: ${txn.date}| amount: ${txn.chargedAmount}| desc: ${txn.description}| status: ${txn.status}`);
        });
      });
    } else {
      throw new Error(scrapeResult.errorType);
    }
  } catch (e) {
    console.error(`Scraping failed for the following reason: ${e.message}`);
  }
})();
