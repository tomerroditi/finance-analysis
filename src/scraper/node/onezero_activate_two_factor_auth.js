import { CompanyTypes, createScraper } from 'israeli-bank-scrapers';

// Get the credentials and other parameters from command line arguments
const args = process.argv.slice(2);
const phoneNumber = args[0];

(async function() {
  try {
    // Define the scraper options
    const options = {
      companyId: CompanyTypes.oneZero,  // Adjust based on the specific bank
      startDate: new Date('2024-05-01'),
      combineInstallments: false,
      showBrowser: false
    };

    const scraper = createScraper(options);
    await scraper.triggerTwoFactorAuth(phoneNumber);
  } catch (e) {
    console.error(`login failed: ${e}`);
  }
})();
