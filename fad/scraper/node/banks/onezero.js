import {CompanyTypes} from 'israeli-bank-scrapers';
import {runScraper} from '../base_scraper.js';

// Get command line arguments
const args = process.argv.slice(2);
const email = args[0];
const password = args[1];
const phoneNumber = args[2];
const otpLongTermToken = args[3];
const start_date = args[4];

// Define scraper options
const options = {
  companyId: CompanyTypes.oneZero,
  startDate: new Date(start_date),
  combineInstallments: false,
  showBrowser: true
};

// Define credentials
const credentials = {
  email: email,
  password: password,
  phoneNumber: phoneNumber,
  otpLongTermToken: otpLongTermToken
};

// Run the scraper with 2FA support
(async function() {
  await runScraper(options, credentials, true);
})();