import { CompanyTypes, createScraper } from 'israeli-bank-scrapers';
import puppeteer from 'puppeteer';
import readline from 'readline';
import path from 'path';
import { homedir } from 'os';
import { mkdirSync } from 'fs';

const args = process.argv.slice(2);
const userCode = args[0];
const password = args[1];
const start_date = args[2];

const BASE_URL = 'https://login.bankhapoalim.co.il';
const LOGIN_URL = `${BASE_URL}/cgi-bin/poalwwwc?reqName=getLogonPage`;
const SUCCESS_URL_PATTERNS = [
  '/portalserver/HomePage',
  '/ng-portals-bt/rb/he/homepage',
  '/ng-portals/rb/he/homepage',
];
const INVALID_PASSWORD_PATTERN = 'errorcode=1.6';
const CHANGE_PASSWORD_PATTERNS = ['/MCP/START', '/ABOUTTOEXPIRE/START'];

function isSuccessUrl(url) {
  return SUCCESS_URL_PATTERNS.some(pattern => url.includes(pattern));
}

function isInvalidPasswordUrl(url) {
  return url.includes(INVALID_PASSWORD_PATTERN);
}

function isChangePasswordUrl(url) {
  return CHANGE_PASSWORD_PATTERNS.some(pattern => url.includes(pattern));
}

function outputResults(scrapeResult) {
  console.log('writing scraped data to console');
  scrapeResult.accounts.forEach((account) => {
    console.log(`found ${account.txns.length} transactions for account number ${account.accountNumber}`);
    account.txns.forEach((txn) => {
      console.log(`account number: ${account.accountNumber}| type: ${txn.type}| id: ${txn.identifier}| date: ${txn.date}| amount: ${txn.chargedAmount}| desc: ${txn.description}| status: ${txn.status}`);
    });
  });
}

async function getOtpFromStdin() {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => {
    console.log('Enter OTP code:');
    rl.question('', (code) => {
      resolve(code.trim());
      rl.close();
    });
  });
}

/**
 * Handle 2FA by logging in manually via Puppeteer and entering the OTP code.
 * After successful 2FA, the browser session cookies will allow a library retry to succeed.
 */
async function handle2faInBrowser(browser) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1024, height: 768 });

  try {
    await page.goto(LOGIN_URL, { waitUntil: 'networkidle2', timeout: 30000 });

    await page.waitForSelector('#userCode', { timeout: 10000 });
    await page.type('#userCode', userCode);
    await page.type('#password', password);
    await page.click('.login-btn');

    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 });

    const currentUrl = page.url();

    if (isSuccessUrl(currentUrl)) {
      await page.close();
      return true;
    }

    if (isInvalidPasswordUrl(currentUrl)) {
      throw new Error('INVALID_PASSWORD: Invalid username or password');
    }

    if (isChangePasswordUrl(currentUrl)) {
      throw new Error('CHANGE_PASSWORD: Password change required by the bank');
    }

    // Unknown page after login - likely a 2FA verification page. Prompt for OTP code.
    const otpCode = await getOtpFromStdin();

    if (otpCode === 'cancel') {
      await page.close();
      return false;
    }

    // Try to find the OTP input field using common selectors
    const otpInput = await page.$('input[type="tel"]')
      || await page.$('input[inputmode="numeric"]')
      || await page.$('input[type="number"]')
      || await page.$('input[autocomplete="one-time-code"]')
      || await page.$('input[type="text"]:not([name="userCode"]):not([name="password"])');

    if (otpInput) {
      await otpInput.click({ clickCount: 3 });
      await otpInput.type(otpCode);

      const submitBtn = await page.$('button[type="submit"]')
        || await page.$('.login-btn')
        || await page.$('input[type="submit"]')
        || await page.$('button.btn-primary');

      if (submitBtn) {
        await submitBtn.click();
      } else {
        await page.keyboard.press('Enter');
      }
    } else {
      // Fallback: type the code via keyboard and press Enter
      await page.keyboard.type(otpCode);
      await page.keyboard.press('Enter');
    }

    // Wait for navigation after OTP submission
    try {
      await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 60000 });
    } catch (e) {
      // Page might update without a full navigation, wait and check URL
      await new Promise(r => setTimeout(r, 5000));
    }

    const newUrl = page.url();
    await page.close();

    if (isSuccessUrl(newUrl)) {
      return true;
    }

    throw new Error('TWO_FACTOR_AUTH: 2FA verification failed - did not reach the home page after entering the code');
  } catch (e) {
    try { await page.close(); } catch {}
    throw e;
  }
}

(async function () {
  let browser;
  try {
    // Persistent browser profile so the bank remembers 2FA sessions across runs
    const dataDir = path.join(homedir(), '.finance-analysis', 'hapoalim-browser-data');
    mkdirSync(dataDir, { recursive: true });

    browser = await puppeteer.launch({
      headless: false,
      userDataDir: dataDir,
    });

    const options = {
      companyId: CompanyTypes.hapoalim,
      startDate: new Date(start_date),
      combineInstallments: false,
      showBrowser: true,
      browser: browser,
      skipCloseBrowser: true,
    };

    const credentials = { userCode, password };
    const scraper = createScraper(options);
    let scrapeResult = await scraper.scrape(credentials);

    if (scrapeResult.success) {
      outputResults(scrapeResult);
    } else if (scrapeResult.errorType === 'GENERAL_ERROR') {
      // GENERAL_ERROR after login typically means the bank redirected to an unrecognized page,
      // which is most commonly a 2FA verification page.
      const twoFaSuccess = await handle2faInBrowser(browser);

      if (twoFaSuccess) {
        // 2FA completed - retry scraping with the authenticated session
        const scraper2 = createScraper(options);
        scrapeResult = await scraper2.scrape(credentials);

        if (scrapeResult.success) {
          outputResults(scrapeResult);
        } else {
          throw new Error(`${scrapeResult.errorType}: Scraping failed after completing 2FA. ${scrapeResult.errorMessage}`);
        }
      } else {
        console.log('2FA was cancelled by user');
      }
    } else {
      throw new Error(`${scrapeResult.errorType}: ${scrapeResult.errorMessage}`);
    }
  } catch (e) {
    console.error(`logging error: ${e.message}`);
  } finally {
    if (browser) {
      try { await browser.close(); } catch {}
    }
  }
})();
