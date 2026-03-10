import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

from scraper.base import ApiScraper
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from scraper.utils.dates import utc_to_israel_date_str
from scraper.utils.fetch import fetch_graphql, fetch_post

logger = logging.getLogger(__name__)

HEBREW_WORDS_REGEX = re.compile(r"[\u0590-\u05FF][\u0590-\u05FF\"'\-_ /\\]*[\u0590-\u05FF]")

IDENTITY_SERVER_URL = "https://identity.tfd-bank.com/v1/"

GRAPHQL_API_URL = "https://mobile.tfd-bank.com/mobile-graph/graphql"

GET_CUSTOMER = """
query GetCustomer {
  customer {
    __typename
    customerId
    userId
    idType
    idNumber
    hebrewFirstName
    hebrewLastName
    latinFirstName
    latinLastName
    dateOfBirth
    lastLoginDate
    userEmail
    gender
    portfolioRelations {
      __typename
      customerId
      customerRole
      portfolioId
      initiator
      relationToInitiator
      status
    }
    portfolios {
      __typename
      ...Portfolio
    }
    status
  }
}
fragment Portfolio on Portfolio {
  __typename
  accounts {
    __typename
    accountId
    accountType
    closingDate
    currency
    openingDate
    status
    subType
  }
  activationDate
  bank
  baseCurrency
  branch
  club
  clubDescription
  iban
  imageURL
  isJointAccount
  partnerName {
    __typename
    partnerFirstName
    partnerLastName
  }
  portfolioId
  portfolioNum
  portfolioType
  status
  subType
  onboardingCompleted
}
"""

GET_MOVEMENTS = """query GetMovements(
  $portfolioId: String!
  $accountId: String!
  $pagination: PaginationInput!
  $language: BffLanguage!
) {
  movements(
    portfolioId: $portfolioId
    accountId: $accountId
    pagination: $pagination
    language: $language
  ) {
    __typename
    ...MovementsFragment
  }
}
fragment TransactionInstrumentAmountFragment on TransactionInstrumentAmount {
  __typename
  instrumentAmount
  instrumentSymbol
  instrumentType
}
fragment CounterPartyReferenceFragment on CounterPartyReference {
  __typename
  bankId
  bic
  branchCode
  id
  name
  type
}
fragment BaseTransactionFragment on BaseTransaction {
  __typename
  accountId
  betweenOwnAccounts
  bookDate
  calculatedStatus
  chargeAmount {
    __typename
    ...TransactionInstrumentAmountFragment
  }
  clearingSystem
  counterParty {
    __typename
    ...CounterPartyReferenceFragment
  }
  currentPaymentNumber
  direction
  domainType
  isReversal
  method
  originalAmount {
    __typename
    ...TransactionInstrumentAmountFragment
  }
  portfolioId
  totalPaymentsCount
  transactionId
  transactionType
  valueDate
}
fragment CategoryFragment on Category {
  __typename
  categoryId
  dataSource
  subCategoryId
}
fragment RecurrenceFragment on Recurrence {
  __typename
  dataSource
  isRecurrent
}
fragment TransactionEnrichmentFragment on TransactionEnrichment {
  __typename
  categories {
    __typename
    ...CategoryFragment
  }
  recurrences {
    __typename
    ...RecurrenceFragment
  }
}
fragment TransactionEventMetadataFragment on TransactionEventMetadata {
  __typename
  correlationId
  processingOrder
}
fragment CounterPartyTransferData on CounterPartyTransfer {
  __typename
  accountId
  bank_id
  branch_code
  counter_party_name
}
fragment BankTransferDetailsData on BankTransferDetails {
  __typename
  ... on CashBlockTransfer {
    counterParty {
      __typename
      ...CounterPartyTransferData
    }
    transferDescriptionKey
  }
  ... on RTGSReturnTransfer {
    transferDescriptionKey
  }
  ... on RTGSTransfer {
    transferDescriptionKey
  }
  ... on SwiftReturnTransfer {
    transferConversionRate
    transferDescriptionKey
  }
  ... on SwiftTransfer {
    transferConversionRate
    transferDescriptionKey
  }
  ... on Transfer {
    counterParty {
      __typename
      ...CounterPartyTransferData
    }
    transferDescriptionKey
  }
}
fragment CategoryData on Category {
  __typename
  categoryId
  dataSource
  subCategoryId
}
fragment RecurrenceData on Recurrence {
  __typename
  dataSource
  isRecurrent
}
fragment CardDetailsData on CardDetails {
  __typename
  ... on CardCharge {
    book_date
    cardDescriptionKey
  }
  ... on CardChargeFCY {
    book_date
    cardConversionRate
    cardDescriptionKey
    cardFCYAmount
    cardFCYCurrency
  }
  ... on CardMonthlySettlement {
    cardDescriptionKey
  }
  ... on CardRefund {
    cardDescriptionKey
  }
  ... on CashBlockCardCharge {
    cardDescriptionKey
  }
}
fragment CashDetailsData on CashDetails {
  __typename
  ... on CashWithdrawal {
    cashDescriptionKey
  }
  ... on CashWithdrawalFCY {
    FCYAmount
    FCYCurrency
    cashDescriptionKey
    conversionRate
  }
}
fragment ChequesDetailsData on ChequesDetails {
  __typename
  ... on CashBlockChequeDeposit {
    bookDate
    chequesDescriptionKey
  }
  ... on ChequeDeposit {
    bookDate
    chequesDescriptionKey
  }
  ... on ChequeReturn {
    bookDate
    chequeReturnReason
    chequesDescriptionKey
  }
  ... on ChequeWithdrawal {
    chequesDescriptionKey
  }
}
fragment DefaultDetailsData on DefaultDetails {
  __typename
  ... on DefaultWithTransaction {
    defaultDescriptionKey
  }
  ... on DefaultWithoutTransaction {
    categories {
      __typename
      ...CategoryData
    }
    defaultDescriptionKey
  }
}
fragment FeeDetailsData on FeeDetails {
  __typename
  ... on GeneralFee {
    feeDescriptionKey
  }
}
fragment LoanDetailsData on LoanDetails {
  __typename
  ... on FullPrePayment {
    loanDescriptionKey
  }
  ... on Initiate {
    loanDescriptionKey
  }
  ... on MonthlyPayment {
    loanDescriptionKey
    loanPaymentNumber
    loanTotalPaymentsCount
  }
  ... on PartialPrePayment {
    loanDescriptionKey
  }
}
fragment MandateDetailsData on MandateDetails {
  __typename
  ... on MandatePayment {
    mandateDescriptionKey
  }
  ... on MandateReturnPayment {
    mandateDescriptionKey
  }
}
fragment SavingsDetailsData on SavingsDetails {
  __typename
  ... on FullSavingsWithdrawal {
    savingsDescriptionKey
  }
  ... on MonthlySavingsDeposit {
    savingsDepositNumber
    savingsDescriptionKey
    savingsTotalDepositCount
  }
  ... on PartialSavingsWithdrawal {
    savingsDescriptionKey
  }
  ... on SavingsClosing {
    savingsDescriptionKey
  }
  ... on SavingsDeposit {
    savingsDescriptionKey
  }
  ... on SavingsInterest {
    savingsDescriptionKey
  }
  ... on SavingsPenalty {
    savingsDescriptionKey
  }
  ... on SavingsTax {
    savingsDescriptionKey
  }
}
fragment SubscriptionDetailsData on SubscriptionDetails {
  __typename
  ... on SubscriptionPayment {
    subscriptionDescriptionKey
  }
  ... on SubscriptionReturnPayment {
    subscriptionDescriptionKey
  }
}
fragment TransactionsDetailsData on TransactionDetails {
  __typename
  ... on BankTransfer {
    bank_transfer_details {
      __typename
      ...BankTransferDetailsData
    }
    book_date
    categories {
      __typename
      ...CategoryData
    }
    recurrences {
      __typename
      ...RecurrenceData
    }
    value_date
  }
  ... on Card {
    card_details {
      __typename
      ...CardDetailsData
    }
    categories {
      __typename
      ...CategoryData
    }
    recurrences {
      __typename
      ...RecurrenceData
    }
    value_date
  }
  ... on Cash {
    cash_details {
      __typename
      ...CashDetailsData
    }
    categories {
      __typename
      ...CategoryData
    }
    recurrences {
      __typename
      ...RecurrenceData
    }
    value_date
  }
  ... on Cheques {
    categories {
      __typename
      ...CategoryData
    }
    chequesDetails {
      __typename
      ...ChequesDetailsData
    }
    recurrences {
      __typename
      ...RecurrenceData
    }
    valueDate
    referenceNumber
    frontImageUrl
    backImageUrl
  }
  ... on Default {
    default_details {
      __typename
      ...DefaultDetailsData
    }
    recurrences {
      __typename
      ...RecurrenceData
    }
    value_date
  }
  ... on Fee {
    categories {
      __typename
      ...CategoryData
    }
    fee_details {
      __typename
      ...FeeDetailsData
    }
    value_date
  }
  ... on Loans {
    categories {
      __typename
      ...CategoryData
    }
    loan_details {
      __typename
      ...LoanDetailsData
    }
    recurrences {
      __typename
      ...RecurrenceData
    }
    value_date
  }
  ... on Mandate {
    categories {
      __typename
      ...CategoryData
    }
    mandate_details {
      __typename
      ...MandateDetailsData
    }
    recurrences {
      __typename
      ...RecurrenceData
    }
    value_date
  }
  ... on Savings {
    categories {
      __typename
      ...CategoryData
    }
    recurrences {
      __typename
      ...RecurrenceData
    }
    savings_details {
      __typename
      ...SavingsDetailsData
    }
    value_date
  }
  ... on SubscriptionTransaction {
    categories {
      __typename
      ...CategoryData
    }
    recurrences {
      __typename
      ...RecurrenceData
    }
    subscription_details {
      __typename
      ...SubscriptionDetailsData
    }
    value_date
  }
}
fragment TransactionFragment on Transaction {
  __typename
  baseTransaction {
    __typename
    ...BaseTransactionFragment
  }
  enrichment {
    __typename
    ...TransactionEnrichmentFragment
  }
  metadata {
    __typename
    ...TransactionEventMetadataFragment
  }
  referenceNumber
  transactionDetails {
    __typename
    ...TransactionsDetailsData
  }
}
fragment MovementFragment on Movement {
  __typename
  accountId
  bankCurrencyAmount
  bookingDate
  conversionRate
  creditDebit
  description
  isReversed
  linkTransaction {
    __typename
    ...TransactionFragment
  }
  movementAmount
  movementCurrency
  movementId
  movementReversedId
  movementTimestamp
  movementType
  portfolioId
  runningBalance
  transaction {
    __typename
    ...TransactionFragment
  }
  valueDate
}
fragment PaginationFragment on Pagination {
  __typename
  cursor
  hasMore
}
fragment MovementsFragment on Movements {
  __typename
  isRunningBalanceInSync
  movements {
    __typename
    ...MovementFragment
  }
  pagination {
    __typename
    ...PaginationFragment
  }
}"""


def _sanitize_hebrew(text: str) -> str:
    """Clean Hebrew strings that use LTR override characters.

    OneZero Hebrew strings are reversed with a unicode control character (U+202D)
    that forces display in LTR order. This function removes the control character
    and reverses Hebrew substrings to restore natural reading order.

    Parameters
    ----------
    text : str
        The raw text that may contain LTR override characters.

    Returns
    -------
    str
        Sanitized text with Hebrew substrings in correct order.
    """
    if "\u202d" not in text:
        return text.strip()

    plain_string = text.replace("\u202d", "").strip()
    hebrew_matches = list(HEBREW_WORDS_REGEX.finditer(plain_string))
    ranges_to_reverse = [
        (m.start(), m.start() + len(m.group())) for m in hebrew_matches
    ]

    out: list[str] = []
    index = 0

    for start, end in ranges_to_reverse:
        out.append(plain_string[index:start])
        index = start
        reversed_segment = plain_string[start:end][::-1]
        out.append(reversed_segment)
        index = end

    out.append(plain_string[index:])

    return "".join(out)


def _extract_result_data(response: dict, key: str) -> any:
    """Extract a value from an API response's ``resultData``.

    Raises a descriptive error when the response indicates failure or
    the expected key is missing, instead of a bare ``KeyError``.

    Parameters
    ----------
    response : dict
        The parsed JSON response from the One Zero API.
    key : str
        The key to extract from ``resultData``.

    Returns
    -------
    any
        The value at ``response["resultData"][key]``.

    Raises
    ------
    Exception
        If the response is missing ``resultData`` or the requested key.
    """
    if not isinstance(response, dict):
        raise Exception(f"Unexpected API response type: {type(response).__name__}")

    result_data = response.get("resultData")
    if result_data is None:
        error_msg = response.get("errorMessage") or response.get("message") or ""
        error_code = response.get("errorCode") or response.get("resultCode") or ""
        detail = f" (code={error_code}, message={error_msg})" if error_code or error_msg else ""
        raise Exception(f"API error — no resultData in response{detail}")

    if key not in result_data:
        raise Exception(
            f"Missing '{key}' in resultData (keys: {list(result_data.keys())})"
        )

    return result_data[key]


class OneZeroScraper(ApiScraper):
    """Scraper for One Zero Bank (https://www.onezerbank.com).

    Uses the One Zero identity server for OTP-based authentication
    and GraphQL API for fetching transaction data.
    """

    _otp_context: Optional[str] = None
    _access_token: Optional[str] = None

    async def _trigger_two_factor_auth(self, phone_number: str) -> dict:
        """Trigger OTP SMS to the user's phone number.

        Parameters
        ----------
        phone_number : str
            Full international phone number starting with '+'.

        Returns
        -------
        dict
            Result dict with 'success' key.

        Raises
        ------
        Exception
            If the phone number format is invalid.
        """
        if not phone_number.startswith("+"):
            raise Exception(
                "A full international phone number starting with + "
                "and a three digit country code is required"
            )

        logger.debug("Fetching device token")
        device_token_response = await fetch_post(
            f"{IDENTITY_SERVER_URL}/devices/token",
            {"extClientId": "mobile", "os": "Android"},
            client=self.client,
        )
        device_token = _extract_result_data(device_token_response, "deviceToken")

        logger.debug("Sending OTP to phone number %s", phone_number)
        otp_prepare_response = await fetch_post(
            f"{IDENTITY_SERVER_URL}/otp/prepare",
            {
                "factorValue": phone_number,
                "deviceToken": device_token,
                "otpChannel": "SMS_OTP",
            },
            client=self.client,
        )
        self._otp_context = _extract_result_data(otp_prepare_response, "otpContext")

        return {"success": True}

    async def _get_long_term_token(self, otp_code: str) -> dict:
        """Exchange an OTP code for a long-term token.

        Parameters
        ----------
        otp_code : str
            The OTP code received via SMS.

        Returns
        -------
        dict
            Result with 'success' and 'long_term_token' keys.

        Raises
        ------
        Exception
            If triggerTwoFactorAuth was not called first.
        """
        if not self._otp_context:
            raise Exception(
                "triggerTwoFactorAuth was not called before getLongTermToken()"
            )

        logger.debug("Requesting OTP token")
        otp_verify_response = await fetch_post(
            f"{IDENTITY_SERVER_URL}/otp/verify",
            {
                "otpContext": self._otp_context,
                "otpCode": otp_code,
            },
            client=self.client,
        )
        otp_token = _extract_result_data(otp_verify_response, "otpToken")
        return {"success": True, "long_term_token": otp_token}

    async def _resolve_otp_token(self) -> str:
        """Resolve the OTP long-term token from credentials or OTP flow.

        Uses the long-term token from credentials if available,
        otherwise triggers the OTP flow via ``on_otp_request`` callback.

        Returns
        -------
        str
            The OTP long-term token.

        Raises
        ------
        Exception
            If neither long-term token nor OTP callback is available.
        """
        otp_long_term_token = self.credentials.get("otpLongTermToken")
        if otp_long_term_token:
            return otp_long_term_token

        phone_number = self.credentials.get("phoneNumber")
        if not phone_number:
            raise Exception(
                "phoneNumber is required when otpLongTermToken is not provided"
            )

        if self.on_otp_request is None:
            raise Exception(
                "on_otp_request callback is required when otpLongTermToken is not provided"
            )

        logger.debug("Triggering OTP flow")
        await self._trigger_two_factor_auth(phone_number)

        otp_code = await self.on_otp_request()

        token_result = await self._get_long_term_token(otp_code)
        return token_result["long_term_token"]

    async def login(self) -> LoginResult:
        """Authenticate with One Zero Bank.

        Resolves the OTP token (from stored long-term token or interactive flow),
        then obtains an ID token and session access token.

        Returns
        -------
        LoginResult
            SUCCESS on successful authentication, UNKNOWN_ERROR on failure.
        """
        try:
            otp_token = await self._resolve_otp_token()
        except Exception as e:
            logger.error("Failed to resolve OTP token: %s", e)
            return LoginResult.UNKNOWN_ERROR

        try:
            logger.debug("Requesting id token")
            id_token_response = await fetch_post(
                f"{IDENTITY_SERVER_URL}/getIdToken",
                {
                    "otpSmsToken": otp_token,
                    "email": self.credentials["email"],
                    "pass": self.credentials["password"],
                    "pinCode": "",
                },
                client=self.client,
            )
            id_token = _extract_result_data(id_token_response, "idToken")

            logger.debug("Requesting session token")
            session_token_response = await fetch_post(
                f"{IDENTITY_SERVER_URL}/sessions/token",
                {
                    "idToken": id_token,
                    "pass": self.credentials["password"],
                },
                client=self.client,
            )
            self._access_token = _extract_result_data(session_token_response, "accessToken")

        except Exception as e:
            logger.error("Login failed: %s", e)
            return LoginResult.UNKNOWN_ERROR

        return LoginResult.SUCCESS

    async def _fetch_portfolio_movements(
        self, portfolio: dict, start_date: date
    ) -> AccountResult:
        """Fetch movements for a single portfolio via GraphQL.

        Parameters
        ----------
        portfolio : dict
            Portfolio data containing 'portfolioId', 'portfolioNum', and 'accounts'.
        start_date : date
            Earliest date for which to include movements.

        Returns
        -------
        AccountResult
            Account result with transactions and balance.
        """
        account = portfolio["accounts"][0]
        cursor = None
        movements: list[dict] = []

        auth_headers = {"authorization": f"Bearer {self._access_token}"}

        while True:
            logger.debug(
                "Fetching transactions for account %s...",
                portfolio["portfolioNum"],
            )
            result = await fetch_graphql(
                GRAPHQL_API_URL,
                GET_MOVEMENTS,
                variables={
                    "portfolioId": portfolio["portfolioId"],
                    "accountId": account["accountId"],
                    "language": "HEBREW",
                    "pagination": {
                        "cursor": cursor,
                        "limit": 50,
                    },
                },
                extra_headers=auth_headers,
                client=self.client,
            )

            movements_data = result["movements"]
            new_movements = movements_data["movements"]
            pagination = movements_data["pagination"]

            # Prepend new movements (they come in reverse chronological order)
            movements = new_movements + movements
            cursor = pagination["cursor"]

            if not pagination["hasMore"]:
                break

            # Check if we've gone past the start date
            if movements and datetime.fromisoformat(
                movements[0]["movementTimestamp"].replace("Z", "+00:00")
            ).date() < start_date:
                break

        # Sort by timestamp ascending
        movements.sort(
            key=lambda m: datetime.fromisoformat(
                m["movementTimestamp"].replace("Z", "+00:00")
            )
        )

        # Filter to only include movements from start_date onwards
        matching_movements = [
            m
            for m in movements
            if datetime.fromisoformat(
                m["movementTimestamp"].replace("Z", "+00:00")
            ).date()
            >= start_date
        ]

        # Calculate balance from last movement's running balance
        balance = 0.0
        if movements:
            balance = float(movements[-1]["runningBalance"])

        transactions = []
        for movement in matching_movements:
            enrichment = (movement.get("transaction") or {}).get("enrichment")
            has_installments = False
            if enrichment:
                recurrences = enrichment.get("recurrences") or []
                has_installments = any(r.get("isRecurrent") for r in recurrences)

            modifier = -1 if movement["creditDebit"] == "DEBIT" else 1
            amount = float(movement["movementAmount"]) * modifier

            transactions.append(
                Transaction(
                    type=(
                        TransactionType.INSTALLMENTS
                        if has_installments
                        else TransactionType.NORMAL
                    ),
                    status=TransactionStatus.COMPLETED,
                    identifier=movement["movementId"],
                    date=utc_to_israel_date_str(movement["valueDate"]),
                    processed_date=utc_to_israel_date_str(movement["movementTimestamp"]),
                    original_amount=amount,
                    original_currency=movement["movementCurrency"],
                    charged_amount=amount,
                    charged_currency=movement["movementCurrency"],
                    description=_sanitize_hebrew(movement["description"]),
                )
            )

        return AccountResult(
            account_number=portfolio["portfolioNum"],
            transactions=transactions,
            balance=balance,
        )

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch account data and transactions from One Zero Bank.

        Returns
        -------
        list[AccountResult]
            List of accounts with their transactions and balances.

        Raises
        ------
        Exception
            If login() was not called or failed.
        """
        if not self._access_token:
            raise Exception("login() was not called")

        default_start = date.today() - timedelta(days=364)
        start_date = self.options.start_date
        effective_start = max(default_start, start_date)

        auth_headers = {"authorization": f"Bearer {self._access_token}"}

        logger.debug("Fetching account list")
        result = await fetch_graphql(
            GRAPHQL_API_URL,
            GET_CUSTOMER,
            variables={},
            extra_headers=auth_headers,
            client=self.client,
        )

        portfolios: list[dict] = []
        for customer in result["customer"]:
            customer_portfolios = customer.get("portfolios") or []
            portfolios.extend(customer_portfolios)

        accounts: list[AccountResult] = []
        for portfolio in portfolios:
            account_result = await self._fetch_portfolio_movements(
                portfolio, effective_start
            )
            accounts.append(account_result)

        return accounts
