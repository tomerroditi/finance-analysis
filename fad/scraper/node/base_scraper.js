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
  const credentialsWithOtp = {  // only for onezero
    email: credentials.email,
    password: credentials.password,
    phoneNumber: credentials.phoneNumber,
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
    // Categorize the error for better handling in Python
    let errorPrefix = "ERROR_GENERAL";
    let errorMessage = e.message;

    // Check for credential errors
    if (e.message.includes("INVALID_PASSWORD") || 
        e.message.includes("INVALID_CREDENTIALS") || 
        e.message.includes("password") || 
        e.message.includes("credentials") ||
        e.message.includes("GENERIC")) {
      errorPrefix = "ERROR_CREDENTIALS";
    }
    // Check for connection errors
    else if (e.message.includes("ENOTFOUND") || 
             e.message.includes("ECONNREFUSED") || 
             e.message.includes("network") ||
             e.message.includes("Network")) {
      errorPrefix = "ERROR_CONNECTION";
    }
    // Check for timeout errors
    else if (e.message.includes("timeout") || 
             e.message.includes("timed out") ||
             e.message.includes("TIMEOUT")) {
      errorPrefix = "ERROR_TIMEOUT";
    }
    // Check for data errors
    else if (e.message.includes("data") || 
             e.message.includes("parsing") ||
             e.message.includes("DATA")) {
      errorPrefix = "ERROR_DATA";
    }
    // Check for login errors
    else if (e.message.includes("login") || 
             e.message.includes("authentication") || 
             e.message.includes("auth") ||
             e.message.includes("LOGIN")) {
      errorPrefix = "ERROR_LOGIN";
    }
    // Check for password change required
    else if (e.message.includes("CHANGE_PASSWORD") || 
             e.message.includes("password expired") ||
             e.message.includes("change password")) {
      errorPrefix = "ERROR_PASSWORD_CHANGE";
    }
    // Check for account-related errors
    else if (e.message.includes("account") || 
             e.message.includes("blocked") || 
             e.message.includes("suspended") ||
             e.message.includes("locked")) {
      errorPrefix = "ERROR_ACCOUNT";
    }
    // Check for service unavailability
    else if (e.message.includes("maintenance") || 
             e.message.includes("unavailable") || 
             e.message.includes("service") ||
             e.message.includes("down")) {
      errorPrefix = "ERROR_SERVICE";
    }
    // Check for rate limiting
    else if (e.message.includes("rate limit") || 
             e.message.includes("too many requests") || 
             e.message.includes("try again later") ||
             e.message.includes("429")) {
      errorPrefix = "ERROR_RATE_LIMIT";
    }
    // Check for security-related issues
    else if (e.message.includes("captcha") || 
             e.message.includes("verification") || 
             e.message.includes("security") ||
             e.message.includes("challenge")) {
      errorPrefix = "ERROR_SECURITY";
    }

    // Log the error with its category for debugging
    console.error(`logging error: ${errorPrefix}: ${errorMessage}`);

    // Add stack trace for more detailed debugging
    console.error(`DEBUG: Error stack trace: ${e.stack}`);

    return { 
      success: false, 
      errorType: errorPrefix,
      errorMessage: errorMessage
    };
  }
}
