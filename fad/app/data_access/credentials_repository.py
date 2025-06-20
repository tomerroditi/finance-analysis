import os
import yaml
import stat
from fad import CREDENTIALS_PATH, SRC_PATH

import keyring
from fad.app.naming_conventions import LoginFields

_KEYRING_SERVICE = "finance-analysis-app"


class CredentialsRepository:
    """
    Manages storage and retrieval of credentials with secure handling of passwords.

    Provides functionality to load, manipulate, and save credentials while securely handling sensitive 
    information such as passwords by leveraging a keyring for secure storage. Ensures file permissions 
    and structure integrity of the credential file to maintain security and consistency.

    Attributes
    ----------
    credentials : dict
        A dictionary containing the loaded credentials from the YAML file.
    _instance : CredentialsRepository or None
        Singleton instance of the repository.
    _initialized : bool
        Flag indicating whether the instance has been initialized.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(CredentialsRepository, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """
        Initialize the CredentialsRepository.

        Implements a singleton pattern to ensure only one instance exists.
        Loads credentials on first initialization.
        """
        if self._initialized:
            return
        self.credentials = self.load_credentials()
        self._initialized = True
    @classmethod
    def _set_file_permissions(cls, path: str) -> None:
        """
        Set restrictive file permissions on the credentials file.

        Attempts to set read/write permissions for the owner only.
        This is a best-effort operation that may not work on all platforms.

        Parameters
        ----------
        path : str
            Path to the file whose permissions should be set.

        Returns
        -------
        None
        """
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass  # On Windows, this may not work; best effort

    def _keyring_key(self, service: str, provider: str, account: str, field: str) -> str:
        """
        Generate a unique key for storing credentials in the keyring.

        Creates a colon-separated string that uniquely identifies a credential field.

        Parameters
        ----------
        service : str
            The type of service (e.g., 'banks', 'credit_cards', 'insurances').
        provider : str
            The name of the service provider.
        account : str
            The name of the account.
        field : str
            The specific credential field (e.g., 'password', 'username').

        Returns
        -------
        str
            A unique key string in the format "service:provider:account:field".
        """
        return f"{service}:{provider}:{account}:{field}"

    def load_credentials(self) -> dict:
        """
        Load credentials from the YAML file or create default if not exists.

        Reads credentials from the YAML file, ensuring the file exists and has the correct
        structure. Creates a default file if none exists. Retrieves passwords from the
        system keyring and injects them into the credentials dictionary.

        Returns
        -------
        dict
            A dictionary containing all user credentials with the structure:
            {service: {provider: {account: {field: value}}}}
        """
        # If file doesn't exist, create with default
        if not os.path.exists(CREDENTIALS_PATH):
            os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)
            with open(os.path.join(SRC_PATH, 'resources', 'default_credentials.yaml'), 'r') as file:
                default_credentials = yaml.safe_load(file)
            with open(CREDENTIALS_PATH, 'w') as file:
                yaml.dump(default_credentials, file, sort_keys=False, indent=4)
            self._set_file_permissions(CREDENTIALS_PATH)

        with open(CREDENTIALS_PATH, 'r') as file:
            credentials = yaml.safe_load(file)

        # Ensure all expected login fields are present and inject passwords from keyring
        for service, providers in credentials.items():
            for provider, accounts in providers.items():
                for account, fields in accounts.items():
                    # Get expected login fields for this provider
                    expected_fields = LoginFields.get_fields(provider)
                    for field in expected_fields:
                        if field not in fields:
                            fields[field] = ""
                        if 'password' in field.lower():
                            key = self._keyring_key(service, provider, account, field)
                            password = keyring.get_password(_KEYRING_SERVICE, key)
                            fields[field] = password or ""
        return credentials

    def save_credentials(self, credentials: dict) -> None:
        """
        Save credentials to the YAML file with secure password handling.

        Cleans up the credentials dictionary by removing empty entries, securely stores
        passwords in the system keyring, and saves the non-sensitive parts to the YAML file.
        Sets appropriate file permissions on the saved file.

        Parameters
        ----------
        credentials : dict
            The credentials dictionary to save, with the structure:
            {service: {provider: {account: {field: value}}}}

        Returns
        -------
        None
        """
        # Remove empty accounts/providers
        while True:
            deleted = False
            for service, providers in credentials.items():
                if providers == {}:
                    continue
                for provider, accounts in list(providers.items()):
                    if len(accounts) == 0:
                        del credentials[service][provider]
                        deleted = True
                        break
                    for account, fields in list(accounts.items()):
                        if len(fields) == 0:
                            del credentials[service][provider][account]
                            deleted = True
                            break
            if not deleted:
                break

        # Store passwords in keyring, save placeholder in YAML
        credentials_to_save = {}
        for service, providers in credentials.items():
            credentials_to_save.setdefault(service, {})
            for provider, accounts in providers.items():
                credentials_to_save[service].setdefault(provider, {})
                for account, fields in accounts.items():
                    credentials_to_save[service][provider].setdefault(account, {})
                    for field, value in fields.items():
                        if 'password' in field.lower():
                            key = self._keyring_key(service, provider, account, field)
                            keyring.set_password(_KEYRING_SERVICE, key, value or "")
                            credentials_to_save[service][provider][account][field] = "your password is safely stored"
                        else:
                            credentials_to_save[service][provider][account][field] = value

        with open(CREDENTIALS_PATH, 'w') as file:
            yaml.dump(credentials_to_save, file, sort_keys=False, indent=4)
        self._set_file_permissions(CREDENTIALS_PATH)
