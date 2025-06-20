import os
import yaml
import stat
from fad import CREDENTIALS_PATH, SRC_PATH

import keyring
from fad.app.naming_conventions import LoginFields

_KEYRING_SERVICE = "finance-analysis-app"


class CredentialsRepository:
    def __init__(self):
        self.credentials = self.load_credentials()

    @classmethod
    def _set_file_permissions(cls, path):
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass  # On Windows, this may not work; best effort

    def _keyring_key(self, service, provider, account, field):
        return f"{service}:{provider}:{account}:{field}"

    def load_credentials(self) -> dict:
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
