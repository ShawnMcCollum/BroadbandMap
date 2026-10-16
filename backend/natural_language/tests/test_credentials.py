"""Credential encryption, restrictive storage, and recovery behavior."""

import os
from pathlib import Path

import pytest

from natural_language.credentials import (
    CredentialStorageUnavailable,
    credential_is_available,
    encrypt_credential,
    require_credential,
)

pytestmark = pytest.mark.django_db


def test_first_save_creates_restrictive_key_and_encrypts_value(key_file: Path) -> None:
    ciphertext = encrypt_credential("secret-provider-token")
    assert ciphertext != "secret-provider-token"
    assert require_credential(ciphertext) == "secret-provider-token"
    if os.name == "posix":
        assert key_file.stat().st_mode & 0o777 == 0o600
        assert key_file.parent.stat().st_mode & 0o777 == 0o700


def test_subsequent_saves_reuse_key(key_file: Path) -> None:
    encrypted = encrypt_credential("first")
    original = key_file.read_bytes()
    encrypt_credential("second", ciphertext_exists=True)
    assert key_file.read_bytes() == original
    assert require_credential(encrypted) == "first"


@pytest.mark.parametrize("material", [None, b"not-a-fernet-key"])
def test_missing_or_malformed_key_never_replaces_saved_ciphertext(
    key_file: Path, material: bytes | None
) -> None:
    ciphertext = encrypt_credential("persisted")
    key_file.unlink()
    if material is not None:
        key_file.write_bytes(material)
    with pytest.raises(CredentialStorageUnavailable):
        require_credential(ciphertext)
    with pytest.raises(CredentialStorageUnavailable):
        encrypt_credential("replacement", ciphertext_exists=True)
    assert not credential_is_available(ciphertext)


def test_tampered_ciphertext_is_unavailable() -> None:
    ciphertext = encrypt_credential("persisted")
    assert not credential_is_available(ciphertext[:-1] + "x")


def test_missing_material_can_be_recreated_only_without_saved_ciphertext(key_file: Path) -> None:
    encrypt_credential("old")
    key_file.unlink()
    with pytest.raises(CredentialStorageUnavailable):
        encrypt_credential("new", ciphertext_exists=True)
    key_file.unlink(missing_ok=True)
    replacement = encrypt_credential("new", ciphertext_exists=False)
    assert require_credential(replacement) == "new"


def test_unreadable_key_is_never_overwritten(
    key_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ciphertext = encrypt_credential("original")
    original_material = key_file.read_bytes()

    def deny_read(self: Path) -> bytes:
        raise PermissionError("private key path")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", deny_read)
        with pytest.raises(CredentialStorageUnavailable):
            encrypt_credential("replacement", ciphertext_exists=False)
    assert key_file.read_bytes() == original_material
    assert require_credential(ciphertext) == "original"
