import os
import stat
from typing import Dict, Optional

import keyring
import yaml

from fad import CREDENTIALS_PATH, SRC_PATH


_KEYRING_SERVICE = "finance-analysis-app"


class CredentialsRepository:
    """
    Data access layer for credentials storage and retrieval.

    Provides basic CRUD operations for credentials data persistence.
    All business logic has been moved to the CredentialsService.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(CredentialsRepository, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the CredentialsRepository singleton."""
        if self._initialized:
            return
        self._initialized = True

    def read_credentials_file(self) -> Optional[Dict]:
        """
        Read credentials from the YAML file.

        Returns
        -------
        Optional[Dict]
            The credentials dictionary from the file, or None if file doesn't exist.
        """
        if not os.path.exists(CREDENTIALS_PATH):
            return None

        with open(CREDENTIALS_PATH, 'r') as file:
            return yaml.safe_load(file)

    def write_credentials_file(self, credentials: Dict) -> None:
        """
        Write credentials to the YAML file.

        Parameters
        ----------
        credentials : Dict
            The credentials dictionary to write to file.
        """
        os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)
        with open(CREDENTIALS_PATH, 'w') as file:
            yaml.dump(credentials, file, sort_keys=False, indent=4)

    def read_default_credentials(self) -> Dict:
        """
        Read the default credentials template.

        Returns
        -------
        Dict
            The default credentials structure.
        """
        with open(os.path.join(SRC_PATH, 'resources', 'default_credentials.yaml'), 'r') as file:
            return yaml.safe_load(file)

    def get_password_from_keyring(self, key: str) -> Optional[str]:
        """
        Retrieve a password from the system keyring.

        Parameters
        ----------
        key : str
            The keyring key for the password.

        Returns
        -------
        Optional[str]
            The password if found, None otherwise.
        """
        return keyring.get_password(_KEYRING_SERVICE, key)

    def set_password_in_keyring(self, key: str, password: str) -> None:
        """
        Store a password in the system keyring.

        Parameters
        ----------
        key : str
            The keyring key for the password.
        password : str
            The password to store.
        """
        keyring.set_password(_KEYRING_SERVICE, key, password or "")

    def set_file_permissions(self, path: str) -> None:
        """
        Set restrictive file permissions on a file.

        Parameters
        ----------
        path : str
            Path to the file whose permissions should be set.
        """
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass  # On Windows, this may not work; best effort
