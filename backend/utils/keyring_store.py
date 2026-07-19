"""Single owner of all OS-keyring access.

Every backend module that needs the OS keyring goes through here: the
per-credential secrets (passwords, OTP tokens), the machine-wide
field-encryption key, demo-mode namespacing, and the insecure-backend
validation. No other backend module may import ``keyring`` directly.

The one deliberate exception is ``backend/uninstall/cleanup.py``, which
keeps its own lazy ``import keyring`` so the standalone uninstall CLI can
still run (and report "keyring unavailable") on machines where the keyring
package or backend is broken. A drift-guard unit test pins its service
names and key format to the constants defined here.
"""

import logging
import os
from typing import Optional

import keyring
import keyring.errors

from backend.config import AppConfig
from backend.errors import ValidationException

logger = logging.getLogger(__name__)

PROD_SERVICE = "finance-analysis-app"
DEMO_SERVICE = f"{PROD_SERVICE}-demo"
SERVICE_NAMES = (PROD_SERVICE, DEMO_SERVICE)

# Machine-wide Fernet key that encrypts the credentials table's fields
# column (see backend/utils/crypto.py). Always stored under PROD_SERVICE —
# it is per-machine, not per-mode.
FIELD_ENCRYPTION_KEY_NAME = "field-encryption-key"

# Backends that either silently drop secrets or write them to plaintext
# files. Storing a password (or the encryption key) there defeats the
# whole point of keyring-backed storage.
_INSECURE_BACKEND_MODULE_PREFIXES = (
    "keyring.backends.fail",
    "keyring.backends.null",
    "keyrings.alt",
)


def ensure_secure_backend() -> None:
    """Fail loudly when the active keyring backend cannot hold secrets safely.

    Without this check, ``keyring`` silently degrades on machines with no
    keystore daemon: secrets appear saved but land in a null backend (lost)
    or a plaintext file (leaked). An explicit ``PYTHON_KEYRING_BACKEND``
    env var counts as a deliberate operator choice (CI uses a plaintext
    backend on purpose), as does ``FAD_ALLOW_INSECURE_KEYRING=1``.

    Raises
    ------
    ValidationException
        If the resolved backend is a known-insecure one and no explicit
        override is set.
    """
    if os.environ.get("FAD_ALLOW_INSECURE_KEYRING") == "1":
        return
    if os.environ.get("PYTHON_KEYRING_BACKEND"):
        return

    backend = keyring.get_keyring()
    module = type(backend).__module__
    if module.startswith(_INSECURE_BACKEND_MODULE_PREFIXES):
        raise ValidationException(
            "No secure OS keyring backend is available "
            f"(active backend: {module}.{type(backend).__qualname__}). "
            "Secrets cannot be stored safely on this machine. Install/unlock "
            "your OS keyring (Windows Credential Manager, macOS Keychain, "
            "or a Secret Service daemon on Linux), or explicitly opt in to "
            "an insecure backend with FAD_ALLOW_INSECURE_KEYRING=1."
        )


def active_credentials_service() -> str:
    """Keyring service name for credential secrets, demo-aware.

    Returns
    -------
    str
        ``finance-analysis-app``, or the ``-demo`` variant when the app is
        in demo mode so dummy demo secrets never pollute real entries.
    """
    return DEMO_SERVICE if AppConfig().is_demo_mode else PROD_SERVICE


def credential_secret_name(
    service: str, provider: str, account_name: str, field: str
) -> str:
    """Build the canonical keyring entry name for a credential field.

    Parameters
    ----------
    service : str
        Financial service name (e.g. ``"banks"``, ``"credit_cards"``).
    provider : str
        Provider name within the service (e.g. ``"hapoalim"``).
    account_name : str
        Identifier of the account.
    field : str
        Credential field name (e.g. ``"password"``, ``"otpLongTermToken"``).

    Returns
    -------
    str
        Underscore-delimited entry name used as the keyring "username".
    """
    return f"{service}_{provider}_{account_name}_{field}"


def get_secret(service_name: str, secret_name: str) -> Optional[str]:
    """Read a secret from the OS keyring.

    Returns
    -------
    Optional[str]
        The stored value, or None when no entry exists.
    """
    return keyring.get_password(service_name, secret_name)


def set_secret(service_name: str, secret_name: str, value: str) -> None:
    """Store a secret in the OS keyring.

    Validates the active backend first — writing to a null/plaintext
    backend raises instead of silently losing or leaking the secret.
    """
    ensure_secure_backend()
    keyring.set_password(service_name, secret_name, value)


def delete_secret(service_name: str, secret_name: str) -> bool:
    """Delete a secret from the OS keyring.

    Returns
    -------
    bool
        True when an entry was deleted, False when none existed (a
        missing entry is not an error).
    """
    try:
        keyring.delete_password(service_name, secret_name)
        return True
    except keyring.errors.PasswordDeleteError:
        return False
