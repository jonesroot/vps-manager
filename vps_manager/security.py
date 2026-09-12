"""
vps_manager.security
~~~~~~~~~~~~~~~~~~~~

Cryptographic services, secret vault management, path sanitization,
and strict OS-level file permission enforcement across POSIX and Windows.

:copyright: (c) 2025 by Elite Systems Architecture.
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
import platform
import secrets
import stat
import sys
from typing import Final, Self

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from vps_manager.models import VPSManagerError


# ============================================================================
# SECURITY DOMAIN EXCEPTIONS
# ============================================================================


class SecurityError(VPSManagerError):
    """Base exception for all cryptographic and permission safety violations."""


class InsecureFilePermissionsError(SecurityError):
    """Raised when a sensitive configuration or key file has overly permissive ACLs."""


class EncryptionError(SecurityError):
    """Raised when payload encryption fails."""


class DecryptionError(SecurityError):
    """Raised when authentication tag verification or payload decryption fails."""


class PathTraversalError(SecurityError):
    """Raised when a user-supplied path attempts to escape canonical boundaries."""


# ============================================================================
# CONSTANTS & PROTOCOL METRICS
# ============================================================================

VAULT_PREFIX: Final[str] = "enc:v1"
PBKDF2_ITERATIONS: Final[int] = 600_000
SALT_SIZE_BYTES: Final[int] = 16
NONCE_SIZE_BYTES: Final[int] = 12
KEY_SIZE_BYTES: Final[int] = 32  # 256-bit AES key


# ============================================================================
# FILESYSTEM AUDITOR & PERMISSION ENFORCER
# ============================================================================


class FileSecurity:
    """Hardened filesystem helper providing boundary checks and ACL audits."""

    @staticmethod
    def get_default_config_dir() -> Path:
        """Resolve the OS-idiomatic, secure base configuration path.

        - Linux: ~/.config/vps_manager
        - macOS: ~/Library/Application Support/vps_manager
        - Windows: %LOCALAPPDATA%\\vps_manager
        """
        system: str = platform.system().lower()
        home: Path = Path.home()

        if system == "windows":
            local_appdata: str | None = os.environ.get("LOCALAPPDATA")
            base_dir = Path(local_appdata) if local_appdata else home / "AppData" / "Local"
            config_dir = base_dir / "vps_manager"
        elif system == "darwin":
            config_dir = home / "Library" / "Application Support" / "vps_manager"
        else:
            xdg_config: str | None = os.environ.get("XDG_CONFIG_HOME")
            base_dir = Path(xdg_config) if xdg_config else home / ".config"
            config_dir = base_dir / "vps_manager"

        FileSecurity.enforce_private_directory_permissions(config_dir)
        return config_dir

    @staticmethod
    def enforce_private_directory_permissions(directory_path: Path) -> None:
        """Create directory if absent and lock down permissions to user-only (0700)."""
        directory_path.mkdir(parents=True, exist_ok=True)
        if sys.platform != "win32":
            current_mode = stat.S_IMODE(directory_path.stat().st_mode)
            if current_mode != 0o700:
                os.chmod(directory_path, 0o700)

    @staticmethod
    def enforce_private_file_permissions(file_path: Path) -> None:
        """Enforce strict user-only read/write (0600) on sensitive credential files.

        Raises:
            InsecureFilePermissionsError: On POSIX if permissions cannot be hardened.
        """
        if not file_path.exists():
            return

        if sys.platform != "win32":
            st_mode = file_path.stat().st_mode
            # Detect any group or world readability/writability/executability
            insecure_mask = stat.S_IRWXG | stat.S_IRWXO
            if (st_mode & insecure_mask) != 0:
                try:
                    os.chmod(file_path, 0o600)
                except OSError as exc:
                    raise InsecureFilePermissionsError(
                        f"Failed to restrict file permissions for '{file_path}': {exc}"
                    ) from exc

                # Re-verify post chmod
                verified_mode = stat.S_IMODE(file_path.stat().st_mode)
                if verified_mode != 0o600:
                    raise InsecureFilePermissionsError(
                        f"File '{file_path}' has insecure permissions ({oct(verified_mode)}). "
                        f"Expected 0600 (user read/write only)."
                    )

    @staticmethod
    def sanitize_path(untrusted_path: str | Path, *, base_dir: Path | None = None) -> Path:
        """Resolve path to canonical absolute form and guarantee jail boundaries.

        Args:
            untrusted_path: Raw input path from configuration or CLI.
            base_dir: Optional containment root directory.

        Raises:
            PathTraversalError: If path attempts boundary escape or contains null bytes.
        """
        raw_str = str(untrusted_path)
        if "\0" in raw_str:
            raise PathTraversalError("Path contains null-byte characters.")

        # Expand environment variables and home tildes safely
        expanded = os.path.expandvars(os.path.expanduser(raw_str))
        resolved = Path(expanded).resolve()

        if base_dir is not None:
            resolved_base = base_dir.resolve()
            if not resolved.is_relative_to(resolved_base):
                raise PathTraversalError(
                    f"Path '{resolved}' breaches containment boundary '{resolved_base}'."
                )

        return resolved


# ============================================================================
# MASTER KEY MANAGEMENT
# ============================================================================


class MasterKeyManager:
    """Manages the lifecycle, storage, and derivation of the 256-bit vault master key."""

    def __init__(self, key_file_path: Path | None = None) -> None:
        if key_file_path is None:
            self._key_file = FileSecurity.get_default_config_dir() / ".vault.key"
        else:
            self._key_file = key_file_path

    def get_or_create_machine_key(self) -> bytes:
        """Retrieve local machine master key or create a new 256-bit key if absent."""
        parent_dir = self._key_file.parent
        FileSecurity.enforce_private_directory_permissions(parent_dir)

        if self._key_file.exists():
            FileSecurity.enforce_private_file_permissions(self._key_file)
            try:
                raw_bytes = self._key_file.read_bytes()
                key = base64.b64decode(raw_bytes)
                if len(key) != KEY_SIZE_BYTES:
                    raise SecurityError(
                        f"Corrupted master key at '{self._key_file}'. Expected 32 bytes."
                    )
                return key
            except Exception as exc:
                raise SecurityError(f"Failed to read master key: {exc}") from exc

        # Generate new cryptographically random 256-bit key
        new_key = secrets.token_bytes(KEY_SIZE_BYTES)
        encoded_key = base64.b64encode(new_key)

        # Atomic write with tight permissions
        temp_file = self._key_file.with_suffix(".tmp")
        try:
            temp_file.write_bytes(encoded_key)
            FileSecurity.enforce_private_file_permissions(temp_file)
            temp_file.replace(self._key_file)
            FileSecurity.enforce_private_file_permissions(self._key_file)
        except OSError as exc:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            raise SecurityError(f"Failed to persist master key to '{self._key_file}': {exc}") from exc

        return new_key

    @staticmethod
    def derive_key_from_passphrase(passphrase: str, salt: bytes) -> bytes:
        """Derive an AES-256 key from a passphrase using PBKDF2-HMAC-SHA256."""
        if len(salt) != SALT_SIZE_BYTES:
            raise SecurityError(f"KDF salt must be exactly {SALT_SIZE_BYTES} bytes.")

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_SIZE_BYTES,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        return kdf.derive(passphrase.encode("utf-8"))


# ============================================================================
# ZERO-LEAK CRYPTOGRAPHIC SECRET VAULT (AES-256-GCM)
# ============================================================================


class SecretVault:
    """Production-grade AEAD vault for transparent password & key-passphrase encryption."""

    def __init__(self, master_key: bytes) -> None:
        if len(master_key) != KEY_SIZE_BYTES:
            raise SecurityError(f"Master key must be exactly {KEY_SIZE_BYTES} bytes.")
        self._master_key: bytes = master_key
        self._cipher: AESGCM = AESGCM(self._master_key)

    @classmethod
    def with_machine_key(cls, key_file_path: Path | None = None) -> Self:
        """Instantiate vault bound to the local machine master key."""
        manager = MasterKeyManager(key_file_path)
        return cls(manager.get_or_create_machine_key())

    @classmethod
    def with_passphrase(cls, passphrase: str, salt: bytes) -> Self:
        """Instantiate vault derived deterministically from a user-supplied master password."""
        derived_key = MasterKeyManager.derive_key_from_passphrase(passphrase, salt)
        return cls(derived_key)

    def is_encrypted(self, payload: str) -> bool:
        """Verify whether a given string adheres to the vault's sealed container format."""
        return payload.startswith(f"{VAULT_PREFIX}:")

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string into an authenticated, base64-encoded container.

        Format: enc:v1:<nonce_b64>:<ciphertext_with_tag_b64>
        Guarantees idempotency: returns original token if already encrypted.
        """
        if not plaintext:
            return ""

        # Avoid nested/double encryption if payload is already sealed
        if self.is_encrypted(plaintext):
            return plaintext

        nonce = secrets.token_bytes(NONCE_SIZE_BYTES)
        data_bytes = plaintext.encode("utf-8")

        try:
            # AESGCM automatically computes and appends the 16-byte authentication tag
            ciphertext = self._cipher.encrypt(nonce, data_bytes, None)
        except Exception as exc:
            raise EncryptionError(f"AES-GCM encryption failed: {exc}") from exc

        nonce_b64 = base64.urlsafe_b64encode(nonce).decode("ascii")
        ciphertext_b64 = base64.urlsafe_b64encode(ciphertext).decode("ascii")

        return f"{VAULT_PREFIX}:{nonce_b64}:{ciphertext_b64}"

    def decrypt(self, token: str) -> str:
        """Decrypt an authenticated container back into plaintext string.

        Raises:
            DecryptionError: If format is invalid, corrupted, or authentication tag fails.
        """
        if not token:
            return ""

        if not self.is_encrypted(token):
            # Not an encrypted envelope (plaintext fallback during migration)
            return token

        parts = token.split(":")
        if len(parts) != 4 or parts[0] != "enc" or parts[1] != "v1":
            raise DecryptionError("Malformed encrypted token structure.")

        try:
            nonce = base64.urlsafe_b64decode(parts[2].encode("ascii"))
            ciphertext_with_tag = base64.urlsafe_b64decode(parts[3].encode("ascii"))
        except (ValueError, UnicodeError) as exc:
            raise DecryptionError(f"Base64 decoding failed for token: {exc}") from exc

        if len(nonce) != NONCE_SIZE_BYTES:
            raise DecryptionError(f"Corrupted nonce size. Expected {NONCE_SIZE_BYTES} bytes.")

        try:
            decrypted_bytes = self._cipher.decrypt(nonce, ciphertext_with_tag, None)
            return decrypted_bytes.decode("utf-8")
        except InvalidTag as exc:
            raise DecryptionError(
                "Data integrity violation: ciphertext tampered or invalid master key."
            ) from exc
        except UnicodeDecodeError as exc:
            raise DecryptionError("Decrypted payload is not valid UTF-8.") from exc


# ============================================================================
# SSH KEY AUDITOR & SANITIZER
# ============================================================================


class SSHKeyValidator:
    """Audits local private SSH key files for sanity, existence, and permission safety."""

    # Headers conforming to RFC 4716, OpenSSH, and traditional PKCS#1/#8 PEM
    _VALID_KEY_HEADERS: Final[tuple[bytes, ...]] = (
        b"-----BEGIN OPENSSH PRIVATE KEY-----",
        b"-----BEGIN RSA PRIVATE KEY-----",
        b"-----BEGIN DSA PRIVATE KEY-----",
        b"-----BEGIN EC PRIVATE KEY-----",
        b"-----BEGIN PRIVATE KEY-----",
        b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
    )

    @classmethod
    def validate_key_file(cls, key_path_str: str) -> Path:
        """Perform comprehensive audit on an SSH private key file.

        Returns:
            Resolved, canonical Path object.

        Raises:
            ValidationError: If file does not exist, is not a regular file, or has illegal headers.
            InsecureFilePermissionsError: If permissions violate 0600 on POSIX.
        """
        resolved_path = FileSecurity.sanitize_path(key_path_str)

        if not resolved_path.exists():
            raise SecurityError(f"SSH private key file not found: '{resolved_path}'")

        if not resolved_path.is_file():
            raise SecurityError(f"SSH private key path is not a file: '{resolved_path}'")

        # Enforce file permission boundaries
        FileSecurity.enforce_private_file_permissions(resolved_path)

        # Inspect key header signature to ensure user didn't accidentally point to a public key
        try:
            with open(resolved_path, "rb") as f:
                header_chunk = f.read(512).strip()
        except OSError as exc:
            raise SecurityError(f"Unable to read private key '{resolved_path}': {exc}") from exc

        if not any(header in header_chunk for header in cls._VALID_KEY_HEADERS):
            if b"ssh-rsa" in header_chunk or b"ssh-ed25519" in header_chunk:
                raise SecurityError(
                    f"File '{resolved_path}' appears to be a PUBLIC key. "
                    "An SSH PRIVATE key is required."
                )
            raise SecurityError(
                f"File '{resolved_path}' is not a recognized OpenSSH/PEM private key."
            )

        return resolved_path
