from enum import Enum


cc_providers = [
    "amex",
    "behatsdaa",
    "beyahad bishvilha",
    "isracard",
    "max",
    "visa cal",
    "test_credit_card",
    "test_credit_card_2fa",
]

bank_providers = [
    "beinleumi",
    "discount",
    "hapoalim",
    "leumi",
    "massad",
    "mercantile",
    "mizrahi",
    "onezero",
    "otsar hahayal",
    "union",
    "yahav",
    "test_bank",
    "test_bank_2fa",
]


class Services(Enum):
    """
    Enum defining the types of financial services supported by the application.

    Attributes
    ----------
    CREDIT_CARD : str
        Identifier for credit card services.
    BANK : str
        Identifier for banking services.
    INSURANCE : str
        Identifier for insurance services.
    CASH : str
        Identifier for cash services.
    MANUAL_INVESTMENTS : str
        Identifier for manual investment services.
    """

    CREDIT_CARD = "credit_cards"
    BANK = "banks"
    INSURANCE = "insurances"
    CASH = "cash"
    MANUAL_INVESTMENTS = "manual_investments"


class CreditCards(Enum):
    """
    Enum defining supported credit card providers.

    Attributes
    ----------
    MAX : str
        Identifier for MAX credit card.
    VISA_CAL : str
        Identifier for Visa CAL credit card.
    ISRACARD : str
        Identifier for Isracard credit card.
    AMEX : str
        Identifier for American Express credit card.
    BEYAHAD_BISHVILHA : str
        Identifier for Beyahad Bishvilha credit card.
    BEHATSADAA : str
        Identifier for Behatsdaa credit card.
    """

    MAX = "max"
    VISA_CAL = "visa cal"
    ISRACARD = "isracard"
    AMEX = "amex"
    BEYAHAD_BISHVILHA = "beyahad bishvilha"
    BEHATSADAA = "behatsdaa"
    TEST_CREDIT_CARD = "test_credit_card"
    TEST_CREDIT_CARD_2FA = "test_credit_card_2fa"


class Banks(Enum):
    """
    Enum defining supported bank providers.

    Attributes
    ----------
    HAPOALIM : str
        Identifier for Bank Hapoalim.
    LEUMI : str
        Identifier for Bank Leumi.
    DISCOUNT : str
        Identifier for Discount Bank.
    MIZRAHI : str
        Identifier for Mizrahi-Tefahot Bank.
    MERCANTILE : str
        Identifier for Mercantile Bank.
    OTSAR_HAHAYAL : str
        Identifier for Otsar Hahayal Bank.
    UNION : str
        Identifier for Union Bank.
    BEINLEUMI : str
        Identifier for First International Bank (Beinleumi).
    MASSAD : str
        Identifier for Massad Bank.
    YAHAV : str
        Identifier for Bank Yahav.
    ONEZERO : str
        Identifier for One Zero Digital Bank.
    """

    HAPOALIM = "hapoalim"
    LEUMI = "leumi"
    DISCOUNT = "discount"
    MIZRAHI = "mizrahi"
    MERCANTILE = "mercantile"
    OTSAR_HAHAYAL = "otsar hahayal"
    UNION = "union"
    BEINLEUMI = "beinleumi"
    MASSAD = "massad"
    YAHAV = "yahav"
    ONEZERO = "onezero"
    TEST_BANK = "test_bank"
    TEST_BANK_2FA = "test_bank_2fa"


class Fields(Enum):
    """
    Enum defining field names used for credential information.

    These fields represent different types of credential information required
    by various financial service providers.

    Attributes
    ----------
    ID : str
        Field name for ID number.
    CARD_6_DIGITS : str
        Field name for the first 6 digits of a credit card.
    PASSWORD : str
        Field name for password.
    USERNAME : str
        Field name for username.
    USER_CODE : str
        Field name for user code.
    NUM : str
        Field name for a numeric identifier.
    NATIONAL_ID : str
        Field name for national ID number.
    EMAIL : str
        Field name for email address.
    PHONE_NUMBER : str
        Field name for phone number.
    """

    ID = "id"
    CARD_6_DIGITS = "card6Digits"
    PASSWORD = "password"
    USERNAME = "username"
    USER_CODE = "userCode"
    NUM = "num"
    NATIONAL_ID = "nationalID"
    EMAIL = "email"
    PHONE_NUMBER = "phoneNumber"


class LoginFields:
    """
    Class defining the required login fields for different financial service providers.

    This class maintains a mapping of providers to their required login fields,
    and provides a method to retrieve the fields for a specific provider.

    Attributes
    ----------
    providers_fields : dict
        Dictionary mapping provider names to lists of required field names.
    """

    providers_fields = {
        # cards
        "max": ["username", "password"],
        "visa cal": ["username", "password"],
        "isracard": ["id", "card6Digits", "password"],
        "amex": ["id", "card6Digits", "password"],
        "beyahad bishvilha": ["id", "password"],
        "behatsdaa": ["id", "password"],
        # banks
        "hapoalim": ["userCode", "password"],
        "leumi": ["username", "password"],
        "mizrahi": ["username", "password"],
        "discount": ["id", "password", "num"],
        "mercantile": ["id", "password", "num"],
        "otsar hahayal": ["username", "password"],
        "union": ["username", "password"],
        "beinleumi": ["username", "password"],
        "massad": ["username", "password"],
        "yahav": ["username", "nationalID", "password"],
        "onezero": ["email", "password", "phoneNumber"],
        "dummy_tfa": ["email", "password", "phoneNumber"],
        "dummy_tfa_no_otp": ["email", "password", "phoneNumber"],
        "dummy_regular": ["username", "password"],
        # insurances
        "menora": ["username", "password"],
        "clal": ["username", "password"],
        "harel": ["username", "password"],
        "hafenix": ["username", "password"],
        # Test Providers
        "test_bank": ["username", "password"],
        "test_bank_2fa": ["email", "password", "phoneNumber"],
        "test_credit_card": ["username", "password"],
        "test_credit_card_2fa": ["email", "password", "phoneNumber"],
    }

    @staticmethod
    def get_fields(provider: str) -> list[str]:
        """
        Get the required login fields for a specific provider.

        Parameters
        ----------
        provider : str
            The name of the provider (e.g., 'max', 'hapoalim').

        Returns
        -------
        list[str]
            List of field names required for login to the specified provider.
        """
        return LoginFields.providers_fields[provider]
