"""Field-level encryption for credential data at rest.

Non-sensitive credential fields (usernames, national ID numbers, card
digits, phone numbers) live in the SQLite ``credentials`` table. They are
identity-theft-grade PII, and every DB backup carries copies of them, so
they are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) before hitting
disk. The symmetric key is generated once per machine and stored in the OS
Keyring next to the scraper passwords — the DB file (and its backups) are
useless without the OS-level keystore.

Storage format inside the JSON ``fields`` column::

    {"__encrypted__": "<fernet token>"}

Rows written before encryption existed are plain dicts; ``decrypt_fields``
passes them through unchanged and the startup migration
(``CredentialsRepository.encrypt_plaintext_rows``) rewrites them encrypted.
"""

import json
import logging
import os
import threading
from typing import Dict

import keyring
from cryptography.fernet import Fernet, InvalidToken

from backend.errors import ValidationException

logger = logging.getLogger(__name__)

_KEYRING_SERVICE = "finance-analysis-app"
_ENCRYPTION_KEY_NAME = "field-encryption-key"
ENCRYPTED_MARKER = "__encrypted__"

_fernet: Fernet | None = None
_fernet_lock = threading.Lock()

# Backends that either silently drop secrets or write them to plaintext
# files. Storing the encryption key (or a scraper password) there defeats
# the whole point of keyring-backed storage.
_INSECURE_BACKEND_MODULE_PREFIXES = (
    "keyring.backends.fail",
    "keyring.backends.null",
    "keyrings.alt",
)


def ensure_secure_keyring_backend() -> None:
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


def get_fernet() -> Fernet:
    """Return the process-wide Fernet, creating the key on first use.

    The key lives in the OS Keyring under the app's service name so it is
    never written to the repository, the DB, or any config file.
    """
    global _fernet
    if _fernet is not None:
        return _fernet
    with _fernet_lock:
        if _fernet is None:
            key = keyring.get_password(_KEYRING_SERVICE, _ENCRYPTION_KEY_NAME)
            if key is None:
                ensure_secure_keyring_backend()
                key = Fernet.generate_key().decode()
                keyring.set_password(_KEYRING_SERVICE, _ENCRYPTION_KEY_NAME, key)
                logger.info("Generated new credential field-encryption key")
            _fernet = Fernet(key.encode())
    return _fernet


def encrypt_fields(fields: Dict) -> Dict:
    """Encrypt a credential fields dict into the on-disk envelope format.

    Parameters
    ----------
    fields : Dict
        Plaintext credential fields (no passwords — those live in the
        keyring directly).

    Returns
    -------
    Dict
        ``{"__encrypted__": "<fernet token>"}`` envelope.
    """
    token = get_fernet().encrypt(json.dumps(fields).encode()).decode()
    return {ENCRYPTED_MARKER: token}


def decrypt_fields(stored: Dict) -> Dict:
    """Decrypt a stored fields dict, passing legacy plaintext rows through.

    Parameters
    ----------
    stored : Dict
        The value of the ``fields`` JSON column — either an encryption
        envelope or a legacy plaintext dict.

    Returns
    -------
    Dict
        The plaintext credential fields.

    Raises
    ------
    ValidationException
        If the envelope cannot be decrypted (the keyring key was deleted
        or replaced since the row was written).
    """
    if ENCRYPTED_MARKER not in stored:
        return dict(stored)
    try:
        return json.loads(get_fernet().decrypt(stored[ENCRYPTED_MARKER].encode()))
    except InvalidToken:
        raise ValidationException(
            "Stored credentials could not be decrypted — the encryption key "
            "in the OS keyring is missing or was replaced. Delete and "
            "re-enter the affected credentials."
        )


def is_encrypted(stored: Dict) -> bool:
    """Return True when a stored fields dict is an encryption envelope."""
    return ENCRYPTED_MARKER in stored


def reset_fernet_cache() -> None:
    """Drop the cached Fernet instance (test helper)."""
    global _fernet
    with _fernet_lock:
        _fernet = None
