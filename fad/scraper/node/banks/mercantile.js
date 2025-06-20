import {CompanyTypes} from 'israeli-bank-scrapers';
import {runScraper} from '../base_scraper.js';

// Get command line arguments
const args = process.argv.slice(2);
const id = args[0];
const password = args[1];
const num = args[2];
const start_date = args[3];

// Define scraper options
const options = {
  companyId: CompanyTypes.mercantile,
  startDate: new Date(start_date),
  combineInstallments: false,
  showBrowser: true
};

// Define credentials
const credentials = {
  id: id,
  password: password,
  num: num
};

// Run the scraper
(async function() {
  await runScraper(options, credentials);
})();