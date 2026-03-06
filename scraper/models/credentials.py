from dataclasses import dataclass


@dataclass
class ProviderConfig:
    """Configuration for a financial institution scraper provider.

    Parameters
    ----------
    name : str
        Human-readable provider name.
    required_fields : list[str]
        Required credential field names (keys expected in the credentials dict).
    service : str
        Service type: "banks" or "credit_cards".
    requires_2fa : bool
        Whether the provider requires two-factor authentication.
    """

    name: str
    required_fields: list[str]
    service: str = "banks"
    requires_2fa: bool = False


PROVIDER_CONFIGS: dict[str, ProviderConfig] = {
    # Banks
    "hapoalim": ProviderConfig(
        name="Hapoalim",
        required_fields=["userCode", "password"],
    ),
    "leumi": ProviderConfig(
        name="Leumi",
        required_fields=["username", "password"],
    ),
    "discount": ProviderConfig(
        name="Discount",
        required_fields=["id", "password", "num"],
    ),
    "mercantile": ProviderConfig(
        name="Mercantile",
        required_fields=["id", "password", "num"],
    ),
    "mizrahi": ProviderConfig(
        name="Mizrahi",
        required_fields=["username", "password"],
    ),
    "otsar hahayal": ProviderConfig(
        name="Otsar Hahayal",
        required_fields=["username", "password"],
    ),
    "union": ProviderConfig(
        name="Union",
        required_fields=["username", "password"],
    ),
    "beinleumi": ProviderConfig(
        name="Beinleumi",
        required_fields=["username", "password"],
    ),
    "massad": ProviderConfig(
        name="Massad",
        required_fields=["username", "password"],
    ),
    "yahav": ProviderConfig(
        name="Yahav",
        required_fields=["username", "nationalID", "password"],
    ),
    "onezero": ProviderConfig(
        name="OneZero",
        required_fields=["email", "password", "phoneNumber"],
        requires_2fa=True,
    ),
    "pagi": ProviderConfig(
        name="Pagi",
        required_fields=["username", "password"],
    ),
    # Credit cards
    "max": ProviderConfig(
        name="Max",
        required_fields=["username", "password"],
        service="credit_cards",
    ),
    "visa cal": ProviderConfig(
        name="Visa Cal",
        required_fields=["username", "password"],
        service="credit_cards",
    ),
    "isracard": ProviderConfig(
        name="Isracard",
        required_fields=["id", "card6Digits", "password"],
        service="credit_cards",
    ),
    "amex": ProviderConfig(
        name="Amex",
        required_fields=["id", "card6Digits", "password"],
        service="credit_cards",
    ),
    "beyahad bishvilha": ProviderConfig(
        name="Beyahad Bishvilha",
        required_fields=["id", "password"],
        service="credit_cards",
    ),
    "behatsdaa": ProviderConfig(
        name="Behatsdaa",
        required_fields=["id", "password"],
        service="credit_cards",
    ),
    # Insurances
    "hafenix": ProviderConfig(
        name="HaPhoenix",
        required_fields=["id", "phoneNumber"],
        service="insurances",
        requires_2fa=True,
    ),
}
