"""Business logic for financial-provider credential management."""

import contextlib
from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from backend.config import AppConfig
from backend.constants.providers import (
    Fields,
    LoginFields,
    Services,
    bank_providers,
    cc_providers,
    insurance_providers,
)
from backend.errors import EntityNotFoundException, ValidationException
from backend.repositories.credentials_repository import (
    _SENSITIVE_FIELDS,
    CredentialsRepository,
)
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.utils.phone_numbers import ISRAELI_MOBILE_RE, normalize_israeli_mobile

# ``{service: {provider: {account_name: {field: value}}}}``
CredentialsTree = dict[str, dict[str, dict[str, dict[str, Any]]]]

# In-memory credentials cache, partitioned by the resolved database path.
# Real mode, demo mode and every per-visitor demo sandbox resolve to a
# different file, so keying by path keeps them from ever serving each
# other's credentials.
_credentials_cache: dict[str, CredentialsTree] = {}


def cache_key() -> str:
    """Return the cache partition for the current context (its DB path)."""
    return AppConfig().get_db_path()


# Sentinel returned by the API in place of stored secret values. Clients send
# it back unchanged on save to mean "keep the stored value".
MASK_SENTINEL = "__unchanged__"

# Providers whose login sends ``phoneNumber`` verbatim to an API that only
# accepts the international ``+9725XXXXXXXX`` form.
_INTERNATIONAL_PHONE_PROVIDERS = frozenset({"onezero"})


def _require_israeli_mobile(fields: dict[str, Any]) -> None:
    """Normalize ``fields["phoneNumber"]`` in place to ``+9725XXXXXXXX``.

    Parameters
    ----------
    fields : dict
        One account's credential fields, about to be persisted.

    Raises
    ------
    ValidationException
        If the phone number is not a recognisable Israeli mobile number.
    """
    phone = fields.get(Fields.PHONE_NUMBER.value)
    if phone is None:
        return
    normalized = normalize_israeli_mobile(str(phone))
    if not ISRAELI_MOBILE_RE.match(normalized):
        raise ValidationException(
            "Phone number must be an Israeli mobile number in the format +9725XXXXXXXX"
        )
    fields[Fields.PHONE_NUMBER.value] = normalized


class CredentialsService:
    """Service for managing user credentials for financial services.

    Credentials are stored in a DB-backed repository (non-sensitive fields)
    with passwords kept in the OS Keyring. An in-memory cache
    (``_credentials_cache``) avoids repeated DB/Keyring lookups. All
    mutation operations invalidate the cache.

    Parameters
    ----------
    db : Session
        SQLAlchemy session for database operations.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CredentialsRepository(db)
        self.credentials = self.load_credentials()

    def load_credentials(self) -> CredentialsTree:
        """Load all credentials with passwords retrieved from the OS Keyring.

        Uses the in-memory cache if available; otherwise fetches from the
        repository (which reads the DB and Keyring) and populates the cache.

        Returns
        -------
        CredentialsTree
            Deep copy of the full credentials dict in the form
            ``{service: {provider: {account_name: {field: value}}}}``.
        """
        key = cache_key()
        cached = _credentials_cache.get(key)
        if cached is not None:
            return deepcopy(cached)

        credentials = self.repository.get_all_credentials()
        _credentials_cache[key] = credentials
        return deepcopy(credentials)

    def save_credentials(self, credentials: CredentialsTree) -> None:
        """Save credentials for all provided accounts.

        Iterates the nested credentials dict and persists each account's fields.
        Passwords are stored in the OS Keyring; other fields go to the DB via
        the repository. Empty accounts (no non-empty fields) are skipped.
        Invalidates the cache after saving.

        Parameters
        ----------
        credentials : CredentialsTree
            Nested credentials in the form
            ``{service: {provider: {account_name: {field: value}}}}``.

        Raises
        ------
        ValidationException
            If a provider that needs an international phone number was given
            one that is not an Israeli mobile number.
        """
        for service, providers in credentials.items():
            if not isinstance(providers, dict):
                continue
            for provider, accounts in providers.items():
                if not isinstance(accounts, dict):
                    continue
                for account_name, fields in accounts.items():
                    if not isinstance(fields, dict):
                        continue
                    if not fields or all(not v for v in fields.values()):
                        continue
                    # Fields carrying the mask sentinel mean "keep the stored
                    # value" — drop them so the repository leaves the Keyring
                    # entry untouched. An *empty* secret means the same thing:
                    # the edit form submits every field it renders, so a user
                    # who changed only their username sends ``password: ""``,
                    # and writing that through would blank the stored secret.
                    cleaned = {
                        k: v
                        for k, v in fields.items()
                        if v != MASK_SENTINEL
                        and not (k in _SENSITIVE_FIELDS and v == "")
                    }
                    if not cleaned:
                        continue
                    if provider in _INTERNATIONAL_PHONE_PROVIDERS:
                        _require_israeli_mobile(cleaned)
                    self.repository.save_credentials(
                        service, provider, account_name, cleaned
                    )

        self._invalidate_cache()

    def get_available_data_sources(self) -> list[str]:
        """Get a flat list of all configured data source identifiers.

        Returns
        -------
        list[str]
            Strings in the format ``"service - provider - account_name"``
            for every account in the loaded credentials.
        """
        return [
            f"{service} - {provider} - {account}"
            for service, providers in self.credentials.items()
            for provider, accounts in providers.items()
            for account in accounts
        ]

    def get_data_sources_credentials(self, data_sources: list[str]) -> CredentialsTree:
        """Filter the credentials dict to only include the selected data sources.

        Parameters
        ----------
        data_sources : list[str]
            Account identifiers in the form ``"service - provider - account_name"``
            to keep.

        Returns
        -------
        CredentialsTree
            Filtered credentials dict containing only the specified accounts.
        """
        credentials = deepcopy(self.credentials)

        for service, providers in list(credentials.items()):
            for provider, accounts in list(providers.items()):
                for account in list(accounts.keys()):
                    if f"{service} - {provider} - {account}" not in data_sources:
                        del credentials[service][provider][account]

                if not accounts:
                    del credentials[service][provider]

            if not providers:
                del credentials[service]

        return credentials

    def delete_account(
        self,
        service: str,
        provider: str,
        account: str,
        delete_data: bool = False,
    ) -> dict[str, int]:
        """Disconnect an account, optionally deleting its stored data too.

        Deleting the connection alone is non-destructive: the account's
        transactions, balances and scrape history all survive. Passing
        ``delete_data`` additionally removes the transactions and every record
        that references them.

        Parameters
        ----------
        service : str
            Service type (e.g. ``"banks"``).
        provider : str
            Provider identifier.
        account : str
            Account name.
        delete_data : bool, optional
            When ``False`` (the default) only the connection is removed —
            transactions, balances and scrape history are all kept, so
            re-adding the account resumes where it left off. When ``True`` the
            account's transactions and everything referencing them are deleted
            as well, and the next connection starts with a fresh one-year
            backfill.

        Returns
        -------
        dict[str, int]
            ``{"transactions_deleted": int}`` — zero when ``delete_data`` is
            ``False``.
        """
        result = {"transactions_deleted": 0}

        if delete_data:
            # Order matters: purge the data while the account's identity is
            # still known, then drop the credential.
            from backend.services.transactions_service import TransactionsService

            # A service with no transaction table of its own (nothing to
            # delete) must not block disconnecting the account.
            with contextlib.suppress(ValueError):
                result = TransactionsService(self.db).delete_account_data(
                    service, provider, account
                )

        self.repository.delete_credentials(service, provider, account)

        if delete_data:
            # Only wipe the watermark when the history it refers to is gone.
            # Deleting it while keeping the transactions would force a
            # redundant one-year re-scrape of data already stored.
            ScrapingHistoryRepository(self.db).delete_for_account(
                service, provider, account
            )

        self._invalidate_cache()
        return result

    def get_scraper_credentials(
        self,
        service: str | list[str],
        provider: str | list[str],
        account: str | list[str],
    ) -> CredentialsTree:
        """Fetch credentials for a specific scraper (or multiple scrapers).

        Accepts string or list for each parameter and returns only the
        matching subset of the credentials dict.

        Parameters
        ----------
        service : str or list[str]
            Service type(s) to include.
        provider : str or list[str]
            Provider identifier(s) to include.
        account : str or list[str]
            Account name(s) to include.

        Returns
        -------
        CredentialsTree
            Filtered credentials dict containing only the requested accounts.
        """
        credentials = deepcopy(self.credentials)

        services = [service] if isinstance(service, str) else service
        providers = [provider] if isinstance(provider, str) else provider
        accounts = [account] if isinstance(account, str) else account

        filtered: CredentialsTree = {}
        for svc in services:
            if svc not in credentials:
                continue
            filtered[svc] = {}
            for prov in providers:
                if prov not in credentials[svc]:
                    continue
                filtered[svc][prov] = {}
                for acc in accounts:
                    if acc in credentials[svc][prov]:
                        filtered[svc][prov][acc] = credentials[svc][prov][acc]

        return filtered

    def get_masked_credentials(
        self, service: str, provider: str, account: str
    ) -> dict[str, Any]:
        """Fetch a single account's credential fields with secrets masked.

        Intended for the HTTP API: sensitive values (password, OTP tokens)
        are replaced with :data:`MASK_SENTINEL` so plaintext secrets never
        leave the backend. :meth:`save_credentials` recognizes the sentinel
        and keeps the stored value, so a masked payload round-trips safely
        through an edit form.

        Parameters
        ----------
        service : str
            Service type (e.g. ``"banks"``).
        provider : str
            Provider identifier.
        account : str
            Account name.

        Returns
        -------
        dict[str, Any]
            The account's credential fields with every non-empty sensitive
            field replaced by :data:`MASK_SENTINEL`. Empty if not found.
        """
        filtered = self.get_scraper_credentials(service, provider, account)
        fields = filtered.get(service, {}).get(provider, {}).get(account)
        if fields is None:
            return {}
        return {
            k: (MASK_SENTINEL if k in _SENSITIVE_FIELDS and v else v)
            for k, v in fields.items()
        }

    def get_safe_credentials(self) -> dict[str, dict[str, list[str]]]:
        """Get all credentials with sensitive data (passwords) removed.

        Returns only account names, not any field values.

        Returns
        -------
        dict[str, dict[str, list[str]]]
            Nested dict in the form ``{service: {provider: [account_names]}}``.
        """
        accounts = self.repository.list_accounts()
        safe: dict[str, dict[str, list[str]]] = {}
        for a in accounts:
            safe.setdefault(a["service"], {}).setdefault(a["provider"], [])
            safe[a["service"]][a["provider"]].append(a["account_name"])
        return safe

    def get_accounts_list(self) -> list[dict[str, Any]]:
        """Get a flat list of all configured accounts with their credential health.

        An account ``needs_reentry`` when its stored details cannot be
        decrypted (the keyring's field-encryption key is not the one they were
        written with — e.g. a data directory moved from another machine), or
        when its provider logs in with a password and the OS keyring holds
        none. Either way it cannot scrape until the user re-enters its
        details, and the Data Sources page says so on the account card.

        Never in demo mode. A demo scrape does not authenticate — the adapter
        redirects every provider to a dummy scraper that ignores credentials
        entirely — so there is nothing a demo account could be missing. Demo
        rows are deliberately stored as plaintext with no keyring password
        (the hosted demo has neither an OS keyring nor ``cryptography``), and
        without this the whole demo dataset would wear a "Re-enter details"
        badge for a login that is never performed.

        Returns
        -------
        list[dict[str, Any]]
            List of account dicts with ``service``, ``provider``,
            ``account_name`` and ``needs_reentry`` keys.
        """
        demo = AppConfig().is_demo_mode
        accounts: list[dict[str, Any]] = []
        for status in self.repository.list_account_statuses():
            uses_password = Fields.PASSWORD.value in LoginFields.get_fields(
                status["provider"]
            )
            accounts.append(
                {
                    "service": status["service"],
                    "provider": status["provider"],
                    "account_name": status["account_name"],
                    "needs_reentry": not demo
                    and (
                        not status["fields_readable"]
                        or (uses_password and not status["has_password"])
                    ),
                }
            )
        return accounts

    @staticmethod
    def get_available_providers() -> dict[str, list[str]]:
        """Get the selectable providers per service, with test providers hidden.

        Test providers (``"test_"`` prefix) are hidden in both modes: in demo
        mode the scraper layer transparently redirects the real providers to
        test scrapers.

        Returns
        -------
        dict[str, list[str]]
            Dictionary with keys ``"banks"``, ``"credit_cards"`` and
            ``"insurances"``, each containing a list of provider identifiers.
        """
        banks = [p for p in bank_providers if "test_" not in p]
        ccs = [p for p in cc_providers if "test_" not in p]
        insurances = [p for p in insurance_providers if "test_" not in p]
        return {
            Services.BANK.value: banks,
            Services.CREDIT_CARD.value: ccs,
            Services.INSURANCE.value: insurances,
        }

    def delete_credential(
        self,
        service: str,
        provider: str,
        account_name: str,
        delete_data: bool = False,
    ) -> dict[str, int]:
        """Delete a credential and clean up associated Keyring entries.

        Parameters
        ----------
        service : str
            Service type (e.g. ``"banks"``).
        provider : str
            Provider identifier.
        account_name : str
            Account name whose credentials should be deleted.
        delete_data : bool, optional
            Also delete the account's transactions and scrape history.

        Returns
        -------
        dict[str, int]
            ``{"transactions_deleted": int}``.

        Notes
        -----
        Alias of :meth:`delete_account`. Both names are in use (the API route
        calls this one); they must not drift, so this delegates rather than
        repeating the cleanup.
        """
        return self.delete_account(
            service, provider, account_name, delete_data=delete_data
        )

    def seed_demo_credentials(self) -> None:
        """Seed dummy credentials for demo mode using real provider names.

        Creates credentials for real providers (hapoalim, max, visa cal)
        with dummy login data. The scraper layer redirects these to test
        scrapers in demo mode. Each credential is only inserted if not
        already in the repository.
        """

        def ensure_dummy_cred(
            service: str, provider: str, account: str, creds_payload: dict[str, str]
        ) -> None:
            """Save ``creds_payload`` unless the account already exists."""
            try:
                self.repository.get_credentials(service, provider, account)
            except EntityNotFoundException:
                self.repository.save_credentials(
                    service, provider, account, creds_payload
                )
                self._invalidate_cache()

        ensure_dummy_cred(
            Services.BANK.value,
            "hapoalim",
            "Main Account",
            {Fields.USER_CODE.value: "demo", Fields.PASSWORD.value: "demo"},
        )
        ensure_dummy_cred(
            Services.CREDIT_CARD.value,
            "max",
            "Family Card",
            {Fields.USERNAME.value: "demo", Fields.PASSWORD.value: "demo"},
        )
        ensure_dummy_cred(
            Services.CREDIT_CARD.value,
            "visa cal",
            "Online Shopping",
            {Fields.USERNAME.value: "demo", Fields.PASSWORD.value: "demo"},
        )
        ensure_dummy_cred(
            Services.INSURANCE.value,
            "hafenix",
            "The Cohens",
            {Fields.ID.value: "demo", Fields.PHONE_NUMBER.value: "050-1234567"},
        )

    def _invalidate_cache(self) -> None:
        """Clear the current mode's cache entry and reload."""
        _credentials_cache.pop(cache_key(), None)
        self.credentials = self.load_credentials()

    @staticmethod
    def clear_cache() -> None:
        """Clear the in-memory credentials cache for every partition."""
        _credentials_cache.clear()

    @staticmethod
    def clear_cache_for(db_path: str) -> None:
        """Drop the cache entry of one database file (replaced on disk)."""
        _credentials_cache.pop(db_path, None)
