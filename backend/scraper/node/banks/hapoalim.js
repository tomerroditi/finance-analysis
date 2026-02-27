import {CompanyTypes, createScraper} from 'israeli-bank-scrapers';
import {logScrapeResults} from '../base_scraper.js';

// Get command line arguments
const args = process.argv.slice(2);
const userCode = args[0];
const password = args[1];
const start_date = args[2];

const credentials = {
  userCode: userCode,
  password: password
};

// Error type constants matching Python ErrorType enum
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
  TFA_REQUIRED: "TFA_REQUIRED"
};

/**
 * Checks if a scrape failure was likely caused by a 2FA page redirect.
 * Hapoalim shows a 2FA verification page for unrecognized sessions,
 * which causes the scraper to fail because the redirect URL doesn't
 * match any expected login result (success/invalid password/change password).
 *
 * Important: We avoid treating generic TIMEOUT errors as 2FA since those
 * can be caused by slow networks or bank server issues. Instead we look
 * for specific error patterns that indicate an unexpected page redirect.
 */
function is2FAError(scrapeResult) {
  if (scrapeResult.success) return false;

  const msg = (scrapeResult.errorMessage || '').toLowerCase();
  const type = (scrapeResult.errorType || '').toUpperCase();

  // The library explicitly reports TWO_FACTOR_RETRIEVAL when it detects 2FA
  if (type === 'TWO_FACTOR_RETRIEVAL') return true;

  // When Hapoalim redirects to a 2FA verification page, the page URL
  // doesn't match any known login result. The library reports this as
  // "unexpected login result" — the clearest signal of a 2FA redirect.
  if (msg.includes('unexpected login result')) return true;

  // Navigation timeout specifically during login redirect can indicate
  // the page was redirected to the 2FA page instead of the expected URL.
  if (msg.includes('navigation timeout') || msg.includes('waiting for navigation')) return true;

  return false;
}

/**
 * Categorize an error for the Python error handler.
 * Maps error message keywords to ErrorType enum values that match the Python side.
 */
function categorizeError(message) {
  if (message.includes("INVALID_PASSWORD") || message.includes("INVALID_CREDENTIALS")) {
    return ErrorType.CREDENTIALS;
  }
  if (message.includes("TWO_FACTOR_RETRIEVER_MISSING") || message.includes("TWO_FACTOR_RETRIEVAL")) {
    return ErrorType.TFA_REQUIRED;
  }
  if (message.includes("ENOTFOUND") || message.includes("ECONNREFUSED") ||
      message.includes("network") || message.includes("Network")) {
    return ErrorType.CONNECTION;
  }
  if (message.includes("timeout") || message.includes("timed out") || message.includes("TIMEOUT")) {
    return ErrorType.TIMEOUT;
  }
  if (message.includes("CHANGE_PASSWORD") || message.includes("password expired") ||
      message.includes("change password")) {
    return ErrorType.PASSWORD_CHANGE;
  }
  if (message.includes("blocked") || message.includes("suspended") || message.includes("locked")) {
    return ErrorType.ACCOUNT;
  }
  if (message.includes("LOGIN") || message.includes("login failed")) {
    return ErrorType.LOGIN;
  }
  return ErrorType.GENERAL;
}

(async function() {
  try {
    // Phase 1: Attempt normal scrape with standard timeout
    const options = {
      companyId: CompanyTypes.hapoalim,
      startDate: new Date(start_date),
      combineInstallments: false,
      showBrowser: true,
    };

    const scraper = createScraper(options);
    let scrapeResult = await scraper.scrape(credentials);

    if (scrapeResult.success) {
      logScrapeResults(scrapeResult);
      return;
    }

    // Check if the failure was due to a 2FA page
    if (is2FAError(scrapeResult)) {
      // Signal to Python that 2FA was detected
      console.log('2FA page detected');
      console.log('Please complete the 2FA verification in the browser window.');
      console.log('Retrying with extended timeout to allow 2FA completion...');

      // Phase 2: Retry with a much longer timeout to give user time to complete 2FA
      // The bank's browser window is visible (showBrowser: true), so the user can
      // interact with the 2FA page. After completing 2FA, the page redirects to
      // the homepage, and the scraper's waitForRedirect will succeed.
      const retryOptions = {
        companyId: CompanyTypes.hapoalim,
        startDate: new Date(start_date),
        combineInstallments: false,
        showBrowser: true,
        defaultTimeout: 300000,  // 5 minutes for user to complete 2FA
      };

      const retryScraper = createScraper(retryOptions);
      scrapeResult = await retryScraper.scrape(credentials);

      if (scrapeResult.success) {
        logScrapeResults(scrapeResult);
        return;
      }

      // If still failing after extended wait, report as TFA_REQUIRED error
      const errorMessage = `${scrapeResult.errorType}: ${scrapeResult.errorMessage}`;
      console.error(`logging error: ${ErrorType.TFA_REQUIRED}: 2FA verification was not completed in time. ${errorMessage}`);
      return;
    }

    // Non-2FA failure - categorize and report
    const errorMessage = `${scrapeResult.errorType}: ${scrapeResult.errorMessage}`;
    const errorType = categorizeError(errorMessage);
    console.error(`logging error: ${errorType}: ${errorMessage}`);

  } catch (e) {
    const errorMessage = e.message || String(e);
    const errorType = categorizeError(errorMessage);
    console.error(`logging error: ${errorType}: ${errorMessage}`);
    console.error(`DEBUG: Error stack trace: ${e.stack}`);
  }
})();
