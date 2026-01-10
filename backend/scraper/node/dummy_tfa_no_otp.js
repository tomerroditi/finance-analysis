import readline from "readline";

// Get the credentials and other parameters from command line arguments
const args = process.argv.slice(2);
const email = args[0];
const password = args[1];
const phoneNumber = args[2];
const otpLongTermToken = args[3];
const start_date = args[4];

// Dummy account information to generate fake data
const DUMMY_ACCOUNT = {
  accountNumber: '1234567890',
  balance: 15000.00
};


function generateDummyTransactions(count, startDate) {
  const startTimestamp = new Date(startDate).getTime();
  const now = new Date().getTime();
  const transactions = [];

  const merchants = [
    'Grocery Store', 'Coffee Shop', 'Gas Station', 'Online Shopping',
    'Restaurant', 'Pharmacy', 'Utilities', 'Mobile Service'
  ];

  for (let i = 0; i < count; i++) {
    // Random date between start date and now
    const txnDate = new Date(startTimestamp + Math.random() * (now - startTimestamp));
    const formattedDate = txnDate.toISOString().split('T')[0];

    // Random amount between 10 and 500
    const amount = -(Math.floor(Math.random() * 49000) / 100 + 10).toFixed(2);

    // Random merchant
    const merchant = merchants[Math.floor(Math.random() * merchants.length)];

    transactions.push({
      type: 'normal',
      identifier: `TXN${Date.now()}${i}`,
      date: formattedDate,
      processedDate: formattedDate,
      chargedAmount: amount,
      description: merchant,
      status: 'completed'
    });
  }

  return transactions;
}


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

async function renewLongTermToken() {
  return await otpCodeRetriever()
}


try {
  console.log('starting scraper');
  // Define the scraper options
  const options = {
    companyId: "dummy_tfa",  // Adjust based on the specific bank
    startDate: new Date(start_date),
    combineInstallments: false,
    showBrowser: true
  };

  const credentials = {
    email: email,
    password: password,
    phoneNumber: phoneNumber,
    otpLongTermToken: otpLongTermToken,
  };

  // Generate dummy transactions
  const txnCount = Math.floor(Math.random() * 20) + 5; // 5-25 transactions
  const transactions = generateDummyTransactions(txnCount, start_date);

  // Create the result object
  const scrapeResult = {
    success: true,
    accounts: [
      {
        accountNumber: DUMMY_ACCOUNT.accountNumber,
        txns: transactions
      }
    ]
  };

  if (scrapeResult.success) {
    scrapeResultsToConsole(scrapeResult);
  } else {
    throw new Error(`${scrapeResult.errorType}: ${scrapeResult.errorMessage}`);
  }
} catch (e) {
  console.error(`logging error: ${e.message}`);
}



