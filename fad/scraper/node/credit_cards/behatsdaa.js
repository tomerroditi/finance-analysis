import {CompanyTypes} from 'israeli-bank-scrapers';
import {runScraper} from '../base_scraper.js';

// Get command line arguments
const args = process.argv.slice(2);
const id = args[0];
const password = args[1];
const start_date = args[2];

// Define scraper options
const options = {
  companyId: CompanyTypes.behatsdaa,
  startDate: new Date(start_date),
  combineInstallments: false,
  showBrowser: true
};

// Define credentials
const credentials = {
  id: id,
  password: password
};

// Run the scraper
(async function() {
  await runScraper(options, credentials);
})();