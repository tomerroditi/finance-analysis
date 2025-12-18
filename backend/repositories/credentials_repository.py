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


# Default paths - can be overridden via environment variables
USER_DIR = os.environ.get('FAD_USER_DIR', os.path.join(os.path.expanduser('~'), '.finance-analysis'))
CREDENTIALS_PATH = os.environ.get('FAD_CREDENTIALS_PATH', os.path.join(USER_DIR, 'credentials.yaml'))
SRC_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

    def __init__(self, credentials_path: str = CREDENTIALS_PATH):
        """Initialize the CredentialsRepository singleton."""
        if self._initialized:
            return
        self.credentials_path = credentials_path
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

        with open(self.credentials_path, 'r') as file:
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
        with open(self.credentials_path, 'w') as file:
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
            fad_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'fad')
            resources_path = os.path.join(fad_path, 'resources')
        
        file_path = os.path.join(resources_path, 'default_credentials.yaml')
        with open(file_path, 'r') as file:
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
            keyring.delete_password(_KEYRING_SERVICE, key)
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
