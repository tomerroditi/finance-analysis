import { fileURLToPath } from 'url';
import { dirname } from 'path';

// Get the credentials and other parameters from command line arguments
const args = process.argv.slice(2);
const start_date = args[0]; // First argument is start_date as per Python script

// Dummy account information to generate fake data
const DUMMY_ACCOUNT = {
    accountNumber: 'REG-123456',
    balance: 25000.00
};

function generateDummyTransactions(count, startDate) {
    const startTimestamp = new Date(startDate).getTime();
    const now = new Date().getTime();
    const transactions = [];

    const merchants = [
        'Supermarket', 'Cinema', 'Gas Station', 'Electric Company',
        'Water Bill', 'Internet Provider', 'Gym Membership', 'Restaurant'
    ];

    for (let i = 0; i < count; i++) {
        // Random date between start date and now
        const txnDate = new Date(startTimestamp + Math.random() * (now - startTimestamp));
        const formattedDate = txnDate.toISOString().split('T')[0];

        // Random amount between 10 and 1000
        const amount = -(Math.floor(Math.random() * 99000) / 100 + 10).toFixed(2);

        // Random merchant
        const merchant = merchants[Math.floor(Math.random() * merchants.length)];

        transactions.push({
            type: 'normal',
            identifier: `TXN-REG-${Date.now()}-${i}`,
            date: formattedDate,
            processedDate: formattedDate,
            chargedAmount: amount,
            description: merchant,
            status: 'completed'
        });
    }

    return transactions;
}

function scrapeResultsToConsole(scrapeResult) {
    // Print standard success message
    console.log('found 1 transactions for account number ' + DUMMY_ACCOUNT.accountNumber); // Mock count for log parsing if needed, but the loop below handles actual data

    scrapeResult.accounts.forEach((account) => {
        console.log(`found ${account.txns.length} transactions for account number ${account.accountNumber}`);
        account.txns.forEach((txn) => {
            console.log(`account number: ${account.accountNumber}| type: ${txn.type}| id: ${txn.identifier}| date: ${txn.date}| amount: ${txn.chargedAmount}| desc: ${txn.description}| status: ${txn.status}`);
        });
    });
}

try {
    console.log('starting scraper');

    const txnCount = Math.floor(Math.random() * 10) + 3; // 3-13 transactions
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
        throw new Error('Simulation failed');
    }
} catch (e) {
    console.error(`logging error: ${e.message}`);
    process.exit(1);
}
