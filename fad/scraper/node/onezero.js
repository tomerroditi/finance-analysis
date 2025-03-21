import { CompanyTypes, createScraper } from 'israeli-bank-scrapers';
import readline from "readline";

// Get the credentials and other parameters from command line arguments
const args = process.argv.slice(2);
const email = args[0];
const password = args[1];
const phoneNumber = args[2];
const otpLongTermToken = args[3];
const start_date = args[4];


async function otpCodeRetriever() {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });

  return new Promise((resolve, reject) => {
    console.log('Enter OTP code: ');
    rl.question('', (otpCode) => {
      resolve(otpCode);
      rl.close();
    });
  });
}


function scrapeResultsToConsole(scrapeResult) {
  console.log('writing scraped data to console')
  scrapeResult.accounts.forEach((account) => {
    console.log(`found ${account.txns.length} transactions for account number ${account.accountNumber}`);
    account.txns.forEach((txn) => {
      console.log(`account number: ${account.accountNumber}| type: ${txn.type}| id: ${txn.identifier}| date: ${txn.date}| amount: ${txn.chargedAmount}| desc: ${txn.description}| status: ${txn.status}`);
    });
  });
}

function renewLongTermToken(scraper) {
  return new Promise(async (resolve, reject) => {
    const credentials = {
      email: email,
      password: password,
      phoneNumber: phoneNumber,
      otpCodeRetriever: otpCodeRetriever
    }
    const otpTokenResult = await scraper.resolveOtpToken(credentials);
    if (otpTokenResult.success) {
      resolve(otpTokenResult.longTermTwoFactorAuthToken);
    } else {
      reject(new Error(`${otpTokenResult.errorType}: ${otpTokenResult.errorMessage}`));
    }
  });
}


try {
  console.log('starting scraper');
  // Define the scraper options
  const options = {
    companyId: CompanyTypes.oneZero,  // Adjust based on the specific bank
    startDate: new Date(start_date),
    combineInstallments: false,
    showBrowser: false
  };

  const scraper = createScraper(options);
  const credentials = {
    email: email,
    password: password,
    phoneNumber: phoneNumber,
    otpLongTermToken: otpLongTermToken,
  };

  let scrapeResult
  scrapeResult = await scraper.scrape(credentials);

  // renew the long term token if needed
  if (!scrapeResult.success && scrapeResult.errorMessage.includes('reading \'idToken\'')) {
    credentials.otpLongTermToken = await renewLongTermToken(scraper);
    console.log('renewed long term token:', credentials.otpLongTermToken);
    scrapeResult = await scraper.scrape(credentials);
  } else {
    console.log('long term token is valid')
  }

  if (scrapeResult.success) {
    scrapeResultsToConsole(scrapeResult);
  } else {
    throw new Error(`${scrapeResult.errorType}: ${scrapeResult.errorMessage}`);
  }
} catch (e) {
  console.error(`logging error: ${e.message}`);
}

