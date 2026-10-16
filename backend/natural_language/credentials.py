"""Authenticated encryption for the single installation credential."""

import os
import tempfile
from contextlib import suppress
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class CredentialStorageUnavailable(Exception):
    """Credential material is missing, invalid, unreadable, or unwritable."""


def _key_path() -> Path:
    return Path(settings.AI_CREDENTIALS_KEY_FILE)


def _read_key(*, may_create: bool, ciphertext_exists: bool) -> bytes:
    path = _key_path()
    try:
        data = path.read_bytes()
        Fernet(data)
        return data
    except FileNotFoundError:
        pass
    except OSError:
        raise CredentialStorageUnavailable from None
    except ValueError:
        if ciphertext_exists or not may_create:
            raise CredentialStorageUnavailable from None

    if not may_create or ciphertext_exists:
        raise CredentialStorageUnavailable
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        key = Fernet.generate_key()
        # NamedTemporaryFile owns its descriptor, including on failed writes.
        # Closing the raw descriptor again after a context manager exits could
        # close an unrelated descriptor reused by another request thread.
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=".ai-key-", dir=path.parent, delete=False
            ) as stream:
                temporary_name = stream.name
                os.chmod(temporary_name, 0o600)
                stream.write(key)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, path)
        finally:
            if temporary_name is not None:
                with suppress(OSError):
                    os.unlink(temporary_name)
        return key
    except OSError:
        raise CredentialStorageUnavailable from None


def encrypt_credential(value: str, *, ciphertext_exists: bool = False) -> str:
    try:
        key = _read_key(may_create=True, ciphertext_exists=ciphertext_exists)
        return Fernet(key).encrypt(value.encode("utf-8")).decode("ascii")
    except (InvalidToken, OSError, UnicodeError, ValueError):
        raise CredentialStorageUnavailable from None


def credential_is_available(ciphertext: str) -> bool:
    if not ciphertext:
        return False
    try:
        key = _read_key(may_create=False, ciphertext_exists=True)
        Fernet(key).decrypt(ciphertext.encode("ascii"))
        return True
    except (CredentialStorageUnavailable, InvalidToken, UnicodeError, ValueError):
        return False


def require_credential(ciphertext: str) -> str:
    if not ciphertext:
        raise CredentialStorageUnavailable
    try:
        key = _read_key(may_create=False, ciphertext_exists=True)
        return Fernet(key).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (CredentialStorageUnavailable, InvalidToken, UnicodeError, ValueError):
        raise CredentialStorageUnavailable from None
