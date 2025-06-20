import {CompanyTypes, createScraper} from 'israeli-bank-scrapers';
import readline from "readline";

/**
 * Creates an OTP code retriever function for 2FA
 * @returns {Promise<string>} - Promise that resolves with the OTP code
 */
export function otpCodeRetriever() {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });

  return new Promise((resolve) => {
    console.log('Enter OTP code: ');
    rl.question('', (otpCode) => {
      resolve(otpCode);
      rl.close();
    });
  });
}

/**
 * Renews the long term token for 2FA
 * @param {Object} scraper - The scraper object
 * @param {Object} credentials - The credentials object
 * @returns {Promise<string>} - Promise that resolves with the new long term token
 */
export async function renewLongTermToken(scraper, credentials) {
  const credentialsWithOtp = {
    ...credentials,
    otpCodeRetriever: otpCodeRetriever
  };
  
  const otpTokenResult = await scraper.resolveOtpToken(credentialsWithOtp);
  if (otpTokenResult.success) {
    console.log('renewed long term token:', otpTokenResult.longTermTwoFactorAuthToken);
    return otpTokenResult.longTermTwoFactorAuthToken;
  } else {
    throw new Error(`${otpTokenResult.errorType}: ${otpTokenResult.errorMessage}`);
  }
}

/**
 * Logs the scrape results to the console
 * @param {Object} scrapeResult - The scrape result object
 */
export function logScrapeResults(scrapeResult) {
  console.log('writing scraped data to console');
  scrapeResult.accounts.forEach((account) => {
    console.log(`found ${account.txns.length} transactions for account number ${account.accountNumber}`);
    account.txns.forEach((txn) => {
      console.log(`account number: ${account.accountNumber}| type: ${txn.type}| id: ${txn.identifier}| date: ${txn.date}| amount: ${txn.chargedAmount}| desc: ${txn.description}| status: ${txn.status}`);
    });
  });
}

/**
 * Runs the scraper with the given options and credentials
 * @param {Object} options - The scraper options
 * @param {Object} credentials - The credentials object
 * @param {boolean} requires2FA - Whether the scraper requires 2FA
 * @returns {Promise<Object>} - Promise that resolves with the scrape result
 */
export async function runScraper(options, credentials, requires2FA = false) {
  try {
    const scraper = createScraper(options);
    let scrapeResult = await scraper.scrape(credentials);

    // Handle 2FA if needed
    if (requires2FA && !scrapeResult.success && scrapeResult.errorMessage && 
        scrapeResult.errorMessage.includes('reading \'idToken\'')) {
      credentials.otpLongTermToken = await renewLongTermToken(scraper, credentials);
      scrapeResult = await scraper.scrape(credentials);
    } else if (requires2FA) {
      console.log('long term token is valid');
    }

    if (scrapeResult.success) {
      logScrapeResults(scrapeResult);
    } else {
      throw new Error(`${scrapeResult.errorType}: ${scrapeResult.errorMessage}`);
    }
    
    return scrapeResult;
  } catch (e) {
    console.error(`logging error: ${e.message}`);
    return { success: false, errorMessage: e.message };
  }
}