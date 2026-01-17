"""
Credentials repository for secure credential storage.

This repository handles file-based and keyring storage for credentials.
No Streamlit dependencies - uses pure file I/O and system keyring.
"""

import os
import stat
from typing import Dict, Optional

import keyring
import yaml

from backend.errors import EntityNotFoundException


from backend.config import AppConfig

_KEYRING_SERVICE = "finance-analysis-app"


class CredentialsRepository:
    """
    Repository for secure credential storage and retrieval.

    Uses system keyring for passwords and YAML files for non-sensitive data.
    Implemented as a singleton.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(CredentialsRepository, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, credentials_path: str = None):
        """Initialize the CredentialsRepository singleton."""
        if self._initialized:
            return
        self.credentials_path = credentials_path or AppConfig().get_credentials_path()
        self._initialized = True

    def read_credentials_file(self) -> Optional[Dict]:
        """
        Read credentials from the YAML file.

        Returns
        -------
        Optional[Dict]
            The credentials dictionary, or None if file doesn't exist.
        """
        if not os.path.exists(self.credentials_path):
            return None

        with open(self.credentials_path, "r") as file:
            return yaml.safe_load(file)

    def write_credentials_file(self, credentials: Dict) -> None:
        """
        Write credentials to the YAML file.

        Parameters
        ----------
        credentials : Dict
            The credentials dictionary to write.
        """
        os.makedirs(os.path.dirname(self.credentials_path), exist_ok=True)
        with open(self.credentials_path, "w") as file:
            yaml.dump(credentials, file, sort_keys=False, indent=4)

    def read_default_credentials(self, resources_path: Optional[str] = None) -> Dict:
        """
        Read the default credentials template.

        Parameters
        ----------
        resources_path : str, optional
            Path to the resources directory.

        Returns
        -------
        Dict
            The default credentials structure.
        """
        if resources_path is None:
            backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            resources_path = os.path.join(backend_path, "resources")

        file_path = os.path.join(resources_path, "default_credentials.yaml")
        with open(file_path, "r") as file:
            return yaml.safe_load(file)

    @property
    def keyring_service(self):
        service = _KEYRING_SERVICE
        if AppConfig().is_test_mode:
            service += "-test"
        return service

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
        return keyring.get_password(self.keyring_service, key)

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
        keyring.set_password(self.keyring_service, key, password or "")

    def delete_password_from_keyring(self, key: str) -> bool:
        """
        Delete a password from the system keyring.

        Parameters
        ----------
        key : str
            The keyring key for the password.

        Returns
        -------
        bool
            True if deleted successfully, False otherwise.
        """
        try:
            keyring.delete_password(self.keyring_service, key)
            return True
        except keyring.errors.PasswordDeleteError:
            return False

    def set_file_permissions(self, path: str) -> None:
        """
        Set restrictive file permissions on a file.

        Parameters
        ----------
        path : str
            Path to the file.
        """
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass  # Best effort on Windows

    def save_credentials(
        self, service: str, provider: str, account_name: str, credentials: Dict
    ) -> None:
        """
        Save credentials securely, using keyring for passwords.
        """
        all_creds = self.read_credentials_file() or {}

        if service not in all_creds:
            all_creds[service] = {}
        if provider not in all_creds[service]:
            all_creds[service][provider] = {}

        password = credentials.pop("password", None)
        long_term_token = credentials.pop(
            "otpLongTermToken", None
        )  # only one zero for now

        for key, val in {
            "password": password,
            "otpLongTermToken": long_term_token,
        }.items():
            if val is not None:
                self.set_password_in_keyring(
                    f"{service}_{provider}_{account_name}_{key}", val
                )

        all_creds[service][provider][account_name] = credentials
        self.write_credentials_file(all_creds)

    def get_credentials(self, service: str, provider: str, account_name: str) -> Dict:
        """
        Retrieve credentials, including passwords from keyring.
        """
        all_creds = self.read_credentials_file() or {}

        try:
            creds = all_creds[service][provider][account_name].copy()
        except KeyError:
            raise EntityNotFoundException(
                f"Credentials for {service} {provider} {account_name} not found"
            )

        creds["password"] = self.get_password_from_keyring(
            f"{service}_{provider}_{account_name}_password"
        )
        return creds

    def update_credentials(
        self, service: str, provider: str, account_name: str, credentials: Dict
    ) -> None:
        """
        Update credentials securely, using keyring for passwords.
        """
        self.save_credentials(service, provider, account_name, credentials)
