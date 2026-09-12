"""
vps_manager.storage
~~~~~~~~~~~~~~~~~~~

ACID-compliant atomic persistence engine with multi-OS file locking,
automatic schema migration, and transparent credential encryption.

:copyright: (c) 2025 by Elite Systems Architecture.
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Final, Self
from uuid import uuid4

# Cross-platform file locking imports
if sys.platform != "win32":
    import fcntl
else:
    import msvcrt

from vps_manager.models import (
    AuthType,
    Server,
    ServerStatus,
    SystemMetrics,
    ValidationError,
    VPSManagerError,
)
from vps_manager.security import FileSecurity, SecretVault


# ============================================================================
# STORAGE EXCEPTIONS
# ============================================================================


class StorageError(VPSManagerError):
    """Base exception for all persistence and repository operations."""


class ServerNotFoundError(StorageError):
    """Raised when querying a server alias or ID that does not exist."""


class DuplicateServerError(StorageError):
    """Raised when attempting to add a server with an existing alias or ID."""


class LockTimeoutError(StorageError):
    """Raised when cross-process file lock cannot be acquired within timeout."""


# ============================================================================
# CONSTANTS & SCHEMA METRICS
# ============================================================================

CURRENT_SCHEMA_VERSION: Final[int] = 2
DEFAULT_CONFIG_FILENAME: Final[str] = "servers.json"
LOCK_FILENAME: Final[str] = ".servers.lock"


# ============================================================================
# CROSS-PLATFORM FILE LOCK
# ============================================================================


class FileLock:
    """Deterministic, multi-OS re-entrant file lock (POSIX fcntl & Windows msvcrt)."""

    def __init__(self, lock_path: Path, timeout_seconds: float = 5.0) -> None:
        self._lock_path: Path = lock_path
        self._timeout_seconds: float = timeout_seconds
        self._file_descriptor: int | None = None

    def acquire(self) -> None:
        """Acquire exclusive file lock, polling with exponential backoff until timeout."""
        start_time = time.monotonic()
        backoff = 0.01

        # Ensure parent directory exists
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        FileSecurity.enforce_private_directory_permissions(self._lock_path.parent)

        flags = os.O_RDWR | os.O_CREAT | os.O_TRUNC
        fd = os.open(str(self._lock_path), flags, 0o600)

        while True:
            try:
                if sys.platform != "win32":
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

                self._file_descriptor = fd
                return
            except (BlockingIOError, OSError):
                if (time.monotonic() - start_time) >= self._timeout_seconds:
                    os.close(fd)
                    raise LockTimeoutError(
                        f"Timed out after {self._timeout_seconds}s waiting for lock: '{self._lock_path}'"
                    )
                time.sleep(backoff)
                backoff = min(0.2, backoff * 1.5)

    def release(self) -> None:
        """Release lock and cleanly close file descriptor."""
        if self._file_descriptor is not None:
            try:
                if sys.platform != "win32":
                    fcntl.flock(self._file_descriptor, fcntl.LOCK_UN)
                else:
                    try:
                        msvcrt.locking(self._file_descriptor, msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                os.close(self._file_descriptor)
            except OSError:
                pass
            finally:
                self._file_descriptor = None

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.release()


# ============================================================================
# SERVER REPOSITORY
# ============================================================================


class ServerRepository:
    """Thread-safe and process-safe JSON repository managing persistent Server entities."""

    def __init__(
        self,
        storage_path: Path | None = None,
        vault: SecretVault | None = None,
    ) -> None:
        """Initialize repository.

        Args:
            storage_path: Path to servers.json. Defaults to OS standard config directory.
            vault: Secret vault used for automatic encryption/decryption of credentials.
        """
        if storage_path is None:
            config_dir = FileSecurity.get_default_config_dir()
            self._storage_path: Path = config_dir / DEFAULT_CONFIG_FILENAME
            self._lock_path: Path = config_dir / LOCK_FILENAME
        else:
            self._storage_path = storage_path.resolve()
            self._lock_path = self._storage_path.parent / f".{self._storage_path.name}.lock"

        self._vault: SecretVault | None = vault

    @property
    def storage_path(self) -> Path:
        """Absolute canonical path to the underlying JSON file."""
        return self._storage_path

    @contextmanager
    def _locked_transaction(self) -> Iterator[None]:
        """Scoped context manager ensuring exclusive execution during I/O operations."""
        lock = FileLock(self._lock_path)
        with lock:
            yield

    # ========================================================================
    # CRUD OPERATIONS
    # ========================================================================

    def list_all(
        self,
        *,
        group: str | None = None,
        tag: str | None = None,
        status: ServerStatus | None = None,
    ) -> list[Server]:
        """Retrieve all servers matching optional filter criteria."""
        with self._locked_transaction():
            servers = self._read_and_parse()

        filtered: list[Server] = servers
        if group is not None:
            filtered = [s for s in filtered if s.group.lower() == group.lower()]
        if tag is not None:
            tag_lower = tag.lower()
            filtered = [s for s in filtered if tag_lower in s.tags]
        if status is not None:
            filtered = [s for s in filtered if s.status == status]

        return sorted(filtered, key=lambda s: s.alias.lower())

    def get_by_alias(self, alias: str) -> Server:
        """Find a single server by its unique alias.

        Raises:
            ServerNotFoundError: If server does not exist.
        """
        trimmed = alias.strip().lower()
        with self._locked_transaction():
            servers = self._read_and_parse()
            for server in servers:
                if server.alias.lower() == trimmed:
                    return server
        raise ServerNotFoundError(f"Server with alias '{alias}' not found.")

    def get_by_id(self, server_id: str) -> Server:
        """Find a single server by its UUID.

        Raises:
            ServerNotFoundError: If server does not exist.
        """
        trimmed = server_id.strip()
        with self._locked_transaction():
            servers = self._read_and_parse()
            for server in servers:
                if server.id == trimmed:
                    return server
        raise ServerNotFoundError(f"Server with ID '{server_id}' not found.")

    def add(self, server: Server) -> None:
        """Persist a new server, enforcing alias and ID uniqueness.

        Raises:
            DuplicateServerError: If alias or ID is already in use.
        """
        with self._locked_transaction():
            servers = self._read_and_parse()

            for existing in servers:
                if existing.alias.lower() == server.alias.lower():
                    raise DuplicateServerError(
                        f"Server with alias '{server.alias}' already exists."
                    )
                if existing.id == server.id:
                    raise DuplicateServerError(f"Server ID '{server.id}' collision detected.")

            # Encrypt secrets transparently before staging
            secured_server = self._encrypt_server_secrets(server)
            servers.append(secured_server)
            self._write_atomic(servers)

    def update(self, server: Server) -> None:
        """Update an existing server entity identified by its immutable ID.

        Raises:
            ServerNotFoundError: If server does not exist.
            DuplicateServerError: If alias change conflicts with another server.
        """
        with self._locked_transaction():
            servers = self._read_and_parse()
            target_index: int | None = None

            for idx, existing in enumerate(servers):
                if existing.id == server.id:
                    target_index = idx
                elif existing.alias.lower() == server.alias.lower():
                    raise DuplicateServerError(
                        f"Cannot update: alias '{server.alias}' is already in use."
                    )

            if target_index is None:
                raise ServerNotFoundError(f"Server with ID '{server.id}' not found.")

            secured_server = self._encrypt_server_secrets(server)
            servers[target_index] = secured_server
            self._write_atomic(servers)

    def delete(self, server_id: str) -> None:
        """Delete server by ID.

        Raises:
            ServerNotFoundError: If target server does not exist.
        """
        with self._locked_transaction():
            servers = self._read_and_parse()
            initial_count = len(servers)
            remaining = [s for s in servers if s.id != server_id]

            if len(remaining) == initial_count:
                raise ServerNotFoundError(f"Cannot delete: Server ID '{server_id}' not found.")

            self._write_atomic(remaining)

    def update_telemetry(
        self,
        server_id: str,
        *,
        status: ServerStatus,
        latency_ms: float | None,
        metrics: SystemMetrics | None,
    ) -> None:
        """Update runtime health status and system telemetry metrics in-place."""
        with self._locked_transaction():
            servers = self._read_and_parse()
            found = False
            for idx, existing in enumerate(servers):
                if existing.id == server_id:
                    servers[idx] = existing.with_status(
                        status=status,
                        latency_ms=latency_ms,
                        metrics=metrics,
                    )
                    found = True
                    break

            if not found:
                raise ServerNotFoundError(f"Server with ID '{server_id}' not found.")

            self._write_atomic(servers)

    def list_groups(self) -> list[str]:
        """Return distinct, alphabetically sorted server groups."""
        with self._locked_transaction():
            servers = self._read_and_parse()
            groups = {s.group for s in servers if s.group}
            return sorted(groups)

    def list_tags(self) -> list[str]:
        """Return distinct, alphabetically sorted tags across all servers."""
        with self._locked_transaction():
            servers = self._read_and_parse()
            tags: set[str] = set()
            for s in servers:
                tags.update(s.tags)
            return sorted(tags)

    # ========================================================================
    # BACKUP & DISASTER RECOVERY
    # ========================================================================

    def export_backup(self, target_archive_path: Path) -> None:
        """Create a safe snapshot copy of the servers database."""
        with self._locked_transaction():
            if not self._storage_path.exists():
                raise StorageError("Cannot export backup: database file does not exist.")
            target_archive_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self._storage_path, target_archive_path)
            FileSecurity.enforce_private_file_permissions(target_archive_path)

    def import_backup(self, source_archive_path: Path, *, merge: bool = False) -> int:
        """Restore database from backup file.

        Args:
            source_archive_path: Source JSON archive.
            merge: If True, merges non-conflicting servers; if False, replaces entirely.

        Returns:
            Number of imported servers.
        """
        if not source_archive_path.exists():
            raise StorageError(f"Backup file '{source_archive_path}' does not exist.")

        with open(source_archive_path, "r", encoding="utf-8") as f:
            try:
                raw_data: object = json.load(f)
            except json.JSONDecodeError as exc:
                raise StorageError(f"Invalid JSON in backup file: {exc}") from exc

        imported_servers = self._parse_json_tree(raw_data)

        with self._locked_transaction():
            if not merge:
                self._write_atomic(imported_servers)
                return len(imported_servers)

            existing = self._read_and_parse()
            existing_aliases = {s.alias.lower() for s in existing}
            existing_ids = {s.id for s in existing}

            added_count = 0
            for imp in imported_servers:
                if imp.alias.lower() not in existing_aliases and imp.id not in existing_ids:
                    existing.append(self._encrypt_server_secrets(imp))
                    existing_aliases.add(imp.alias.lower())
                    existing_ids.add(imp.id)
                    added_count += 1

            self._write_atomic(existing)
            return added_count

    # ========================================================================
    # INTERNAL ATOMIC I/O & PARSING
    # ========================================================================

    def _read_and_parse(self) -> list[Server]:
        """Read data from disk, apply schema migration if needed, and parse models."""
        if not self._storage_path.exists():
            return []

        FileSecurity.enforce_private_file_permissions(self._storage_path)

        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return []
                raw_json: object = json.loads(content)
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"Failed to read database file '{self._storage_path}': {exc}") from exc

        servers = self._parse_json_tree(raw_json)

        # Decrypt passwords if vault is available
        if self._vault:
            decrypted_list: list[Server] = []
            for s in servers:
                dec_pw = self._vault.decrypt(s.password) if s.password else None
                dec_pp = self._vault.decrypt(s.key_passphrase) if s.key_passphrase else None
                if dec_pw != s.password or dec_pp != s.key_passphrase:
                    # Return copy with decrypted in-memory values
                    s = Server(
                        id=s.id,
                        alias=s.alias,
                        host=s.host,
                        port=s.port,
                        user=s.user,
                        auth_type=s.auth_type,
                        password=dec_pw,
                        key_path=s.key_path,
                        key_passphrase=dec_pp,
                        group=s.group,
                        tags=s.tags,
                        connect_timeout=s.connect_timeout,
                        status=s.status,
                        latency_ms=s.latency_ms,
                        metrics=s.metrics,
                        last_checked_epoch=s.last_checked_epoch,
                    )
                decrypted_list.append(s)
            return decrypted_list

        return servers

    def _parse_json_tree(self, raw_data: object) -> list[Server]:
        """Parse raw JSON tree, automatically handling v1 (list) to v2 migrations."""
        results: list[Server] = []

        # Migration Path: Legacy Format (Raw JSON Array)
        if isinstance(raw_data, list):
            for item in raw_data:
                if isinstance(item, Mapping):
                    try:
                        results.append(Server.from_dict(item))
                    except (ValidationError, KeyError):
                        continue
            return results

        # Current Schema v2
        if isinstance(raw_data, Mapping):
            raw_servers = raw_data.get("servers")
            if isinstance(raw_servers, Sequence):
                for item in raw_servers:
                    if isinstance(item, Mapping):
                        try:
                            results.append(Server.from_dict(item))
                        except (ValidationError, KeyError):
                            continue
            return results

        raise StorageError("Unrecognized database JSON structure.")

    def _encrypt_server_secrets(self, server: Server) -> Server:
        """Ensure password and private key passphrases are encrypted via Vault."""
        if not self._vault:
            return server

        enc_pw = self._vault.encrypt(server.password) if server.password else None
        enc_pp = self._vault.encrypt(server.key_passphrase) if server.key_passphrase else None

        if enc_pw == server.password and enc_pp == server.key_passphrase:
            return server

        return Server(
            id=server.id,
            alias=server.alias,
            host=server.host,
            port=server.port,
            user=server.user,
            auth_type=server.auth_type,
            password=enc_pw,
            key_path=server.key_path,
            key_passphrase=enc_pp,
            group=server.group,
            tags=server.tags,
            connect_timeout=server.connect_timeout,
            status=server.status,
            latency_ms=server.latency_ms,
            metrics=server.metrics,
            last_checked_epoch=server.last_checked_epoch,
        )

    def _write_atomic(self, servers: Sequence[Server]) -> None:
        """Write server list atomically via temporary file rename swap."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        FileSecurity.enforce_private_directory_permissions(self._storage_path.parent)

        payload: dict[str, object] = {
            "version": CURRENT_SCHEMA_VERSION,
            "updated_at": time.time(),
            "servers": [s.to_dict(include_secrets=True) for s in servers],
        }

        # Encode JSON deterministically with indentation
        json_bytes = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")

        # Unique tempfile in the exact same directory (guarantees same filesystem for atomic rename)
        temp_filename = f".{self._storage_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        temp_path = self._storage_path.parent / temp_filename

        try:
            with open(temp_path, "wb") as f:
                f.write(json_bytes)
                f.flush()
                os.fsync(f.fileno())

            FileSecurity.enforce_private_file_permissions(temp_path)

            # Atomic swap
            temp_path.replace(self._storage_path)
            FileSecurity.enforce_private_file_permissions(self._storage_path)

        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise StorageError(f"Atomic write failed for '{self._storage_path}': {exc}") from exc
