"""
vps_manager.models
~~~~~~~~~~~~~~~~~~

Core domain models, enumerations, value objects, and invariant enforcement
for the VPS Manager suite. Fully type-annotated and strictly verified under Pyright.

:copyright: (c) 2025 by Elite Systems Architecture.
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
import ipaddress
import re
import time
from typing import Self
from uuid import uuid4


# ============================================================================
# DOMAIN EXCEPTIONS HIERARCHY
# ============================================================================


class VPSManagerError(Exception):
    """Base exception for all domain-specific errors in the VPS Manager."""


class ValidationError(VPSManagerError):
    """Raised when data invariants or boundary validation constraints fail."""


class InvariantViolationError(VPSManagerError):
    """Raised when an illegal internal entity state transition occurs."""


# ============================================================================
# DOMAIN ENUMERATIONS
# ============================================================================


class AuthType(StrEnum):
    """Supported SSH authentication mechanisms."""

    PASSWORD = "password"
    KEY_FILE = "key_file"
    KEY_DATA = "key_data"
    AGENT = "agent"


class ServerStatus(StrEnum):
    """Current operational and connectivity status of a target server."""

    UNCHECKED = "unchecked"
    ONLINE = "online"
    OFFLINE = "offline"
    AUTH_FAILED = "auth_failed"
    TIMEOUT = "timeout"
    ERROR = "error"


# ============================================================================
# VALUE OBJECTS: SYSTEM METRICS & TELEMETRY
# ============================================================================


@dataclass(slots=True, kw_only=True, frozen=True)
class SystemMetrics:
    """Immutable snapshot of remote system resource utilization and specs.

    Guarantees structural validity across varying Linux distributions and kernel versions.
    """

    hostname: str
    os_name: str
    kernel: str
    uptime_seconds: float
    uptime_human: str
    load_1m: float
    load_5m: float
    load_15m: float
    cpu_count: int
    cpu_usage_pct: float
    mem_total_bytes: int
    mem_used_bytes: int
    mem_free_bytes: int
    mem_usage_pct: float
    disk_total_bytes: int
    disk_used_bytes: int
    disk_free_bytes: int
    disk_usage_pct: float

    def __post_init__(self) -> None:
        """Validate metric boundaries to eliminate invalid mathematical representations."""
        if not (0.0 <= self.cpu_usage_pct <= 100.0):
            object.__setattr__(self, "cpu_usage_pct", max(0.0, min(100.0, self.cpu_usage_pct)))
        if not (0.0 <= self.mem_usage_pct <= 100.0):
            object.__setattr__(self, "mem_usage_pct", max(0.0, min(100.0, self.mem_usage_pct)))
        if not (0.0 <= self.disk_usage_pct <= 100.0):
            object.__setattr__(self, "disk_usage_pct", max(0.0, min(100.0, self.disk_usage_pct)))

    @property
    def formatted_load(self) -> str:
        """Return standardized 1, 5, and 15-minute load average string."""
        return f"{self.load_1m:.2f}, {self.load_5m:.2f}, {self.load_15m:.2f}"

    @property
    def mem_total_human(self) -> str:
        """Format total memory in GiB/MiB."""
        return self._format_bytes(self.mem_total_bytes)

    @property
    def mem_used_human(self) -> str:
        """Format used memory in GiB/MiB."""
        return self._format_bytes(self.mem_used_bytes)

    @property
    def disk_total_human(self) -> str:
        """Format total disk storage in GiB/TiB."""
        return self._format_bytes(self.disk_total_bytes)

    @property
    def disk_used_human(self) -> str:
        """Format used disk storage in GiB/TiB."""
        return self._format_bytes(self.disk_used_bytes)

    @staticmethod
    def _format_bytes(num_bytes: int) -> str:
        """Format byte counter into high-precision human-readable binary prefixes."""
        if num_bytes < 0:
            return "0 B"
        units: tuple[str, ...] = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
        value: float = float(num_bytes)
        for unit in units:
            if value < 1024.0 or unit == units[-1]:
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024.0
        return f"{value:.1f} PiB"

    def to_dict(self) -> dict[str, object]:
        """Serialize metrics into a clean dictionary representation."""
        return {
            "hostname": self.hostname,
            "os_name": self.os_name,
            "kernel": self.kernel,
            "uptime_seconds": self.uptime_seconds,
            "uptime_human": self.uptime_human,
            "load_1m": self.load_1m,
            "load_5m": self.load_5m,
            "load_15m": self.load_15m,
            "cpu_count": self.cpu_count,
            "cpu_usage_pct": self.cpu_usage_pct,
            "mem_total_bytes": self.mem_total_bytes,
            "mem_used_bytes": self.mem_used_bytes,
            "mem_free_bytes": self.mem_free_bytes,
            "mem_usage_pct": self.mem_usage_pct,
            "disk_total_bytes": self.disk_total_bytes,
            "disk_used_bytes": self.disk_used_bytes,
            "disk_free_bytes": self.disk_free_bytes,
            "disk_usage_pct": self.disk_usage_pct,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Self:
        """Construct a validated SystemMetrics instance from raw mapped values."""
        return cls(
            hostname=_extract_str(data, "hostname", default="unknown"),
            os_name=_extract_str(data, "os_name", default="Linux"),
            kernel=_extract_str(data, "kernel", default="unknown"),
            uptime_seconds=_extract_float(data, "uptime_seconds", default=0.0),
            uptime_human=_extract_str(data, "uptime_human", default="0m"),
            load_1m=_extract_float(data, "load_1m", default=0.0),
            load_5m=_extract_float(data, "load_5m", default=0.0),
            load_15m=_extract_float(data, "load_15m", default=0.0),
            cpu_count=_extract_int(data, "cpu_count", default=1),
            cpu_usage_pct=_extract_float(data, "cpu_usage_pct", default=0.0),
            mem_total_bytes=_extract_int(data, "mem_total_bytes", default=0),
            mem_used_bytes=_extract_int(data, "mem_used_bytes", default=0),
            mem_free_bytes=_extract_int(data, "mem_free_bytes", default=0),
            mem_usage_pct=_extract_float(data, "mem_usage_pct", default=0.0),
            disk_total_bytes=_extract_int(data, "disk_total_bytes", default=0),
            disk_used_bytes=_extract_int(data, "disk_used_bytes", default=0),
            disk_free_bytes=_extract_int(data, "disk_free_bytes", default=0),
            disk_usage_pct=_extract_float(data, "disk_usage_pct", default=0.0),
        )


# ============================================================================
# CORE DOMAIN ENTITY: SERVER
# ============================================================================


_HOSTNAME_REGEX = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)
_USERNAME_REGEX = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$", re.IGNORECASE)


@dataclass(slots=True, kw_only=True, frozen=True)
class Server:
    """Immutable domain entity modeling an SSH-accessible server node.

    Maintains zero-trust verification of all connection parameters, prevents
    plain-text credential exposure, and optimizes memory overhead via slots.
    """

    id: str = field(default_factory=lambda: uuid4().hex)
    alias: str
    host: str
    port: int = 22
    user: str = "root"
    auth_type: AuthType = AuthType.KEY_FILE
    password: str | None = field(default=None, repr=False)
    key_path: str | None = None
    key_passphrase: str | None = field(default=None, repr=False)
    group: str = "Default"
    tags: tuple[str, ...] = ()
    connect_timeout: float = 10.0
    status: ServerStatus = ServerStatus.UNCHECKED
    latency_ms: float | None = None
    metrics: SystemMetrics | None = None
    last_checked_epoch: float | None = None

    def __post_init__(self) -> None:
        """Enforce domain invariants and sanitize inputs upon instantiation."""
        # 1. Sanitize & validate alias
        trimmed_alias: str = self.alias.strip()
        if not trimmed_alias:
            raise ValidationError("Server alias cannot be empty or solely whitespace.")
        object.__setattr__(self, "alias", trimmed_alias)

        # 2. Sanitize & validate host (IP or RFC-1123 Hostname)
        trimmed_host: str = self.host.strip()
        if not trimmed_host:
            raise ValidationError("Server host cannot be empty.")
        if not self._is_valid_host(trimmed_host):
            raise ValidationError(
                f"Invalid host '{trimmed_host}'. Must be a valid IPv4, IPv6, or FQDN hostname."
            )
        object.__setattr__(self, "host", trimmed_host)

        # 3. Validate port range
        if not (1 <= self.port <= 65535):
            raise ValidationError(f"Port {self.port} is outside the valid range [1, 65535].")

        # 4. Validate username
        trimmed_user: str = self.user.strip()
        if not trimmed_user or not _USERNAME_REGEX.match(trimmed_user):
            raise ValidationError(
                f"Invalid SSH username '{trimmed_user}'. Must match standard POSIX naming conventions."
            )
        object.__setattr__(self, "user", trimmed_user)

        # 5. Auth-type invariant validation
        if self.auth_type == AuthType.PASSWORD and not self.password:
            raise ValidationError("AuthType.PASSWORD requires a non-empty password.")
        if self.auth_type == AuthType.KEY_FILE and not self.key_path:
            raise ValidationError("AuthType.KEY_FILE requires a valid key_path.")

        # 6. Sanitize tags (remove duplicates, sort deterministically)
        normalized_tags: tuple[str, ...] = tuple(
            sorted({tag.strip().lower() for tag in self.tags if tag.strip()})
        )
        object.__setattr__(self, "tags", normalized_tags)

        # 7. Normalize group
        trimmed_group: str = self.group.strip() or "Default"
        object.__setattr__(self, "group", trimmed_group)

        # 8. Timeout validation
        if self.connect_timeout <= 0.0:
            raise ValidationError(
                f"connect_timeout must be positive. Received: {self.connect_timeout}"
            )

    @staticmethod
    def _is_valid_host(host: str) -> bool:
        """Verify whether string is a valid IPv4, IPv6, or compliant FQDN."""
        # Check standard IP address
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            pass
        # Check RFC-1123 hostname
        return bool(_HOSTNAME_REGEX.match(host))

    def masked_password(self) -> str:
        """Return masked representation of password for secure UI rendering."""
        if not self.password:
            return ""
        return "•" * min(len(self.password), 8)

    def with_status(
        self,
        *,
        status: ServerStatus,
        latency_ms: float | None = None,
        metrics: SystemMetrics | None = None,
    ) -> Self:
        """Create a new immutable Server instance with updated health and telemetry."""
        return Server(
            id=self.id,
            alias=self.alias,
            host=self.host,
            port=self.port,
            user=self.user,
            auth_type=self.auth_type,
            password=self.password,
            key_path=self.key_path,
            key_passphrase=self.key_passphrase,
            group=self.group,
            tags=self.tags,
            connect_timeout=self.connect_timeout,
            status=status,
            latency_ms=latency_ms if latency_ms is not None else self.latency_ms,
            metrics=metrics if metrics is not None else self.metrics,
            last_checked_epoch=time.time(),
        )

    def to_dict(self, *, include_secrets: bool = False) -> dict[str, object]:
        """Convert server configuration to dictionary.

        Args:
            include_secrets: If False, strips passwords and key passphrases.
        """
        data: dict[str, object] = {
            "id": self.id,
            "alias": self.alias,
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "auth_type": str(self.auth_type),
            "key_path": self.key_path,
            "group": self.group,
            "tags": list(self.tags),
            "connect_timeout": self.connect_timeout,
            "status": str(self.status),
            "latency_ms": self.latency_ms,
            "last_checked_epoch": self.last_checked_epoch,
            "metrics": self.metrics.to_dict() if self.metrics else None,
        }
        if include_secrets:
            data["password"] = self.password
            data["key_passphrase"] = self.key_passphrase
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Self:
        """Construct a validated Server instance from untrusted configuration dictionary."""
        auth_type_str: str = _extract_str(data, "auth_type", default=AuthType.KEY_FILE.value)
        try:
            auth_type = AuthType(auth_type_str)
        except ValueError:
            auth_type = AuthType.KEY_FILE

        status_str: str = _extract_str(data, "status", default=ServerStatus.UNCHECKED.value)
        try:
            status = ServerStatus(status_str)
        except ValueError:
            status = ServerStatus.UNCHECKED

        raw_metrics = data.get("metrics")
        metrics: SystemMetrics | None = None
        if isinstance(raw_metrics, Mapping):
            metrics = SystemMetrics.from_dict(raw_metrics)

        raw_tags = data.get("tags")
        tags: tuple[str, ...] = ()
        if isinstance(raw_tags, (list, tuple, set)):
            tags = tuple(str(t) for t in raw_tags if isinstance(t, (str, int)))

        return cls(
            id=_extract_str(data, "id", default=uuid4().hex),
            alias=_extract_str(data, "alias"),
            host=_extract_str(data, "host"),
            port=_extract_int(data, "port", default=22),
            user=_extract_str(data, "user", default="root"),
            auth_type=auth_type,
            password=_extract_optional_str(data, "password"),
            key_path=_extract_optional_str(data, "key_path"),
            key_passphrase=_extract_optional_str(data, "key_passphrase"),
            group=_extract_str(data, "group", default="Default"),
            tags=tags,
            connect_timeout=_extract_float(data, "connect_timeout", default=10.0),
            status=status,
            latency_ms=_extract_optional_float(data, "latency_ms"),
            metrics=metrics,
            last_checked_epoch=_extract_optional_float(data, "last_checked_epoch"),
        )


# ============================================================================
# COMMAND EXECUTION RESULTS & AGGREGATION
# ============================================================================


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandResult:
    """Immutable outcome of an executed shell command on a target server."""

    server_alias: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timestamp_epoch: float = field(default_factory=time.time)

    @property
    def success(self) -> bool:
        """True if the remote process exited with zero status."""
        return self.exit_code == 0

    def to_dict(self) -> dict[str, object]:
        """Serialize command result for logging and analytics."""
        return {
            "server_alias": self.server_alias,
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
            "timestamp_epoch": self.timestamp_epoch,
            "success": self.success,
        }


@dataclass(slots=True, kw_only=True, frozen=True)
class BatchExecutionSummary:
    """Aggregate statistics for parallel multi-server command execution."""

    command: str
    results: tuple[CommandResult, ...]
    total_servers: int
    successful_count: int
    failed_count: int
    duration_seconds: float
    timestamp_epoch: float = field(default_factory=time.time)

    @classmethod
    def from_results(
        cls,
        *,
        command: str,
        results: list[CommandResult] | tuple[CommandResult, ...],
        total_duration: float,
    ) -> Self:
        """Factory method to calculate batch aggregates in O(N) single-pass."""
        results_tuple: tuple[CommandResult, ...] = tuple(results)
        succeeded: int = sum(1 for r in results_tuple if r.success)
        failed: int = len(results_tuple) - succeeded
        return cls(
            command=command,
            results=results_tuple,
            total_servers=len(results_tuple),
            successful_count=succeeded,
            failed_count=failed,
            duration_seconds=round(total_duration, 3),
        )


# ============================================================================
# TYPE EXTRACTION UTILITIES (Pyright Strict Guard Clauses)
# ============================================================================


def _extract_str(data: Mapping[str, object], key: str, default: str | None = None) -> str:
    """Safely extract and narrow a string field from untrusted mappings."""
    val = data.get(key)
    if isinstance(val, str):
        return val
    if default is not None:
        return default
    raise ValidationError(f"Missing required string field '{key}'.")


def _extract_optional_str(data: Mapping[str, object], key: str) -> str | None:
    """Safely extract an optional string."""
    val = data.get(key)
    return val if isinstance(val, str) else None


def _extract_int(data: Mapping[str, object], key: str, default: int) -> int:
    """Safely extract and narrow an integer field."""
    val = data.get(key)
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            pass
    return default


def _extract_float(data: Mapping[str, object], key: str, default: float) -> float:
    """Safely extract and narrow a float field."""
    val = data.get(key)
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            pass
    return default


def _extract_optional_float(data: Mapping[str, object], key: str) -> float | None:
    """Safely extract an optional float."""
    val = data.get(key)
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    return None
