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

    def save_credentials(self, service: str, provider: str, account_name: str, credentials: Dict) -> None:
        """
        Save credentials securely, using keyring for passwords.
        """
        all_creds = self.read_credentials_file() or {}
        
        if service not in all_creds:
            all_creds[service] = {}
        if provider not in all_creds[service]:
            all_creds[service][provider] = {}
        
        # Non-sensitive info for YAML
        yaml_info = {}
        
        for key, value in credentials.items():
            if key == 'password' or key.endswith('_key') or key == 'secret':
                # Store in keyring
                keyring_key = f"{service}_{provider}_{account_name}_{key}"
                self.set_password_in_keyring(keyring_key, value)
            else:
                yaml_info[key] = value
        
        all_creds[service][provider][account_name] = yaml_info
        self.write_credentials_file(all_creds)

    def get_credentials(self, service: str, provider: str, account_name: str) -> Dict:
        """
        Retrieve credentials, including passwords from keyring.
        """
        all_creds = self.read_credentials_file() or {}
        try:
            creds = all_creds[service][provider][account_name].copy()
            
            # Look for passwords in keyring
            # We check typical sensitive keys. 
            # Note: The usage of LoginFields could be dynamic here, but avoiding circular imports is better.
            sensitive_keys = ['password', 'secret', 'otp_key']
            
            for key in creds.keys():
                if key in sensitive_keys or 'password' in key.lower() or 'secret' in key.lower():
                    # Try modern key format (underscores)
                    keyring_key_new = f"{service}_{provider}_{account_name}_{key}"
                    pwd = self.get_password_from_keyring(keyring_key_new)
                    
                    if not pwd:
                        # Try legacy key format (colons) - used by previous Streamlit app
                        keyring_key_old = f"{service}:{provider}:{account_name}:{key}"
                        pwd = self.get_password_from_keyring(keyring_key_old)
                    
                    if pwd:
                        creds[key] = pwd
                    elif creds.get(key) == "your password is safely stored":
                        # If we have the placeholder but couldn't find the real password, clear it
                        # to avoid showing the placeholder to the user.
                        creds[key] = ""
                        
            return creds
        except KeyError:
            return {}
