from dataclasses import dataclass


@dataclass
class ProviderConfig:
    """Configuration for a financial institution scraper provider.

    Parameters
    ----------
    name : str
        Human-readable provider name.
    credential_fields : list[str]
        Required credential field names (keys expected in the credentials dict).
    provider_type : str
        Either "bank" or "credit_card".
    requires_2fa : bool
        Whether the provider requires two-factor authentication.
    """

    name: str
    credential_fields: list[str]
    provider_type: str = "bank"
    requires_2fa: bool = False


PROVIDER_CONFIGS: dict[str, ProviderConfig] = {
    # Banks
    "hapoalim": ProviderConfig(
        name="Hapoalim",
        credential_fields=["userCode", "password"],
    ),
    "leumi": ProviderConfig(
        name="Leumi",
        credential_fields=["username", "password"],
    ),
    "discount": ProviderConfig(
        name="Discount",
        credential_fields=["id", "password", "num"],
    ),
    "mercantile": ProviderConfig(
        name="Mercantile",
        credential_fields=["id", "password", "num"],
    ),
    "mizrahi": ProviderConfig(
        name="Mizrahi",
        credential_fields=["username", "password"],
    ),
    "otsar hahayal": ProviderConfig(
        name="Otsar Hahayal",
        credential_fields=["username", "password"],
    ),
    "union": ProviderConfig(
        name="Union",
        credential_fields=["username", "password"],
    ),
    "beinleumi": ProviderConfig(
        name="Beinleumi",
        credential_fields=["username", "password"],
    ),
    "massad": ProviderConfig(
        name="Massad",
        credential_fields=["username", "password"],
    ),
    "yahav": ProviderConfig(
        name="Yahav",
        credential_fields=["username", "nationalID", "password"],
    ),
    "onezero": ProviderConfig(
        name="OneZero",
        credential_fields=["email", "password", "phoneNumber"],
        requires_2fa=True,
    ),
    "pagi": ProviderConfig(
        name="Pagi",
        credential_fields=["username", "password"],
    ),
    # Credit cards
    "max": ProviderConfig(
        name="Max",
        credential_fields=["username", "password"],
        provider_type="credit_card",
    ),
    "visa cal": ProviderConfig(
        name="Visa Cal",
        credential_fields=["username", "password"],
        provider_type="credit_card",
    ),
    "isracard": ProviderConfig(
        name="Isracard",
        credential_fields=["id", "card6Digits", "password"],
        provider_type="credit_card",
    ),
    "amex": ProviderConfig(
        name="Amex",
        credential_fields=["id", "card6Digits", "password"],
        provider_type="credit_card",
    ),
    "beyahad bishvilha": ProviderConfig(
        name="Beyahad Bishvilha",
        credential_fields=["id", "password"],
        provider_type="credit_card",
    ),
    "behatsdaa": ProviderConfig(
        name="Behatsdaa",
        credential_fields=["id", "password"],
        provider_type="credit_card",
    ),
}
