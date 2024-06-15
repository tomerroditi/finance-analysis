import { CompanyTypes, createScraper } from 'israeli-bank-scrapers';
import readline from 'readline';

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

    // Read OTP code from stdin
    console.log('Enter OTP code: ');
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout
    });

    rl.question('', async (otpCode) => {
      try {
        const results = await scraper.getLongTermTwoFactorToken(otpCode);
        console.log(results.longTermTwoFactorAuthToken);
      } catch (e) {
        console.error(`Failed to get long-term token: ${e}`);
      }
      rl.close();
    });

  } catch (e) {
    console.error(`login failed: ${e}`);
  }
})();
