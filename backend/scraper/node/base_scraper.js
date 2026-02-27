import { createScraper } from 'israeli-bank-scrapers';
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
      console.log(`account number: ${account.accountNumber}| type: ${txn.type}| id: ${txn.identifier}| date: ${txn.date}| amount: ${txn.chargedAmount}| description: ${txn.description}| status: ${txn.status}`);
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
// Error types that match the Python ErrorType enum
const ErrorType = {
  GENERAL: "GENERAL",
  CREDENTIALS: "CREDENTIALS",
  CONNECTION: "CONNECTION",
  TIMEOUT: "TIMEOUT",
  DATA: "DATA",
  LOGIN: "LOGIN",
  PASSWORD_CHANGE: "PASSWORD_CHANGE",
  ACCOUNT: "ACCOUNT",
  SERVICE: "SERVICE",
  RATE_LIMIT: "RATE_LIMIT",
  SECURITY: "SECURITY",
  TWO_FACTOR_REQUIRED: "TWO_FACTOR_REQUIRED"
};

// Known upstream errorType values from israeli-bank-scrapers that indicate 2FA
const TWO_FACTOR_INDICATORS = [
  'TWO_FACTOR_RETRIEVER_MISSING',
  'UNKNOWN_ERROR',
  'GENERAL_ERROR',
  'GENERIC'
];

// Patterns in error messages that suggest 2FA is the root cause
const TWO_FACTOR_MESSAGE_PATTERNS = [
  'two factor', 'two-factor', '2fa', 'otp',
  'verification code', 'sms code', 'phone verification',
  'additional verification', 'identity verification',
  'elevated privileges', 'unknown session'
];

/**
 * Checks if a failed scrape result likely indicates a 2FA challenge.
 * Hapoalim (and potentially other banks) return GENERIC/UNKNOWN_ERROR when
 * the login is redirected to a 2FA page that the scraper doesn't handle.
 */
function isTwoFactorError(scrapeResult) {
  if (!scrapeResult || scrapeResult.success) return false;

  const errorType = scrapeResult.errorType || '';
  const errorMessage = (scrapeResult.errorMessage || '').toLowerCase();

  // Check if the error message explicitly mentions 2FA patterns
  if (TWO_FACTOR_MESSAGE_PATTERNS.some(p => errorMessage.includes(p))) {
    return true;
  }

  // For GENERIC/UNKNOWN_ERROR errors: check for page navigation failures that
  // indicate the login was redirected somewhere unexpected (likely 2FA page)
  if (TWO_FACTOR_INDICATORS.includes(errorType)) {
    // The scraper waited for known URLs but ended up on a different page
    if (errorMessage.includes('navigation') ||
        errorMessage.includes('waiting for') ||
        errorMessage.includes('waitfor') ||
        errorMessage.includes('unexpected') ||
        errorMessage.includes('failed to find') ||
        errorMessage.includes('did not match')) {
      return true;
    }
  }

  return false;
}

/**
 * Categorizes an error message into the appropriate ErrorType.
 */
function categorizeError(message) {
  // Check for credential errors (but not GENERIC — handled separately)
  if (message.includes("INVALID_PASSWORD") ||
    message.includes("INVALID_CREDENTIALS")) {
    return ErrorType.CREDENTIALS;
  }
  // Check for connection errors
  if (message.includes("ENOTFOUND") ||
    message.includes("ECONNREFUSED") ||
    message.includes("network") ||
    message.includes("Network")) {
    return ErrorType.CONNECTION;
  }
  // Check for timeout errors
  if (message.includes("timeout") ||
    message.includes("timed out") ||
    message.includes("TIMEOUT")) {
    return ErrorType.TIMEOUT;
  }
  // Check for password change required
  if (message.includes("CHANGE_PASSWORD") ||
    message.includes("password expired") ||
    message.includes("change password")) {
    return ErrorType.PASSWORD_CHANGE;
  }
  // Check for account-related errors
  if (message.includes("ACCOUNT_BLOCKED") ||
    message.includes("blocked") ||
    message.includes("suspended") ||
    message.includes("locked")) {
    return ErrorType.ACCOUNT;
  }
  // Check for service unavailability
  if (message.includes("maintenance") ||
    message.includes("unavailable")) {
    return ErrorType.SERVICE;
  }
  // Check for rate limiting
  if (message.includes("rate limit") ||
    message.includes("too many requests") ||
    message.includes("try again later") ||
    message.includes("429")) {
    return ErrorType.RATE_LIMIT;
  }
  // Check for security-related issues
  if (message.includes("captcha") ||
    message.includes("security") ||
    message.includes("challenge")) {
    return ErrorType.SECURITY;
  }
  // Check for login errors
  if (message.includes("login") ||
    message.includes("LOGIN")) {
    return ErrorType.LOGIN;
  }
  // Check for data errors
  if (message.includes("parsing") ||
    message.includes("DATA")) {
    return ErrorType.DATA;
  }
  // GENERIC from upstream often means unrecognized page/redirect — likely credentials issue
  if (message.includes("GENERIC")) {
    return ErrorType.CREDENTIALS;
  }

  return ErrorType.GENERAL;
}

export async function runScraper(options, credentials, requires2FA = false) {
  try {
    const scraper = createScraper(options);
    let scrapeResult = await scraper.scrape(credentials);

    // Handle 2FA if needed (for scrapers with built-in 2FA support like OneZero)
    if (requires2FA && !scrapeResult.success && scrapeResult.errorMessage &&
      (scrapeResult.errorMessage.includes('reading \'idToken\'') ||
        scrapeResult.errorMessage.includes('reading \'otpToken\''))) {
      credentials.otpLongTermToken = await renewLongTermToken(scraper, credentials);
      scrapeResult = await scraper.scrape(credentials);
    } else if (requires2FA) {
      console.log('long term token is valid');
    }

    if (scrapeResult.success) {
      logScrapeResults(scrapeResult);
    } else {
      // Check if this failure is actually a 2FA requirement
      if (isTwoFactorError(scrapeResult)) {
        throw new Error(`TWO_FACTOR_REQUIRED: ${scrapeResult.errorType}: ${scrapeResult.errorMessage}`);
      }
      throw new Error(`${scrapeResult.errorType}: ${scrapeResult.errorMessage}`);
    }

    return scrapeResult;
  } catch (e) {
    let errorType;
    let errorMessage = e.message;

    // If already categorized as 2FA, preserve that
    if (e.message.startsWith('TWO_FACTOR_REQUIRED:')) {
      errorType = ErrorType.TWO_FACTOR_REQUIRED;
    } else {
      errorType = categorizeError(e.message);
    }

    // Log the error with its category for debugging
    console.error(`logging error: ${errorType}: ${errorMessage}`);

    // Add stack trace for more detailed debugging
    console.error(`DEBUG: Error stack trace: ${e.stack}`);

    return {
      success: false,
      errorType: errorType,
      errorMessage: errorMessage
    };
  }
}
