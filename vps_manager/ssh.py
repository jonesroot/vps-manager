"""
vps_manager.ssh
~~~~~~~~~~~~~~~

High-performance, purely asynchronous SSH engine and telemetry harvester
powered by asyncssh. Fully compliant with Linux, macOS, and Windows.

:copyright: (c) 2025 by Elite Systems Architecture.
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
import re
import socket
import time
from typing import Final, cast

import asyncssh

from vps_manager.models import (
    AuthType,
    BatchExecutionSummary,
    CommandResult,
    Server,
    ServerStatus,
    SystemMetrics,
    VPSManagerError,
)
from vps_manager.security import SSHKeyValidator, SecretVault


# ============================================================================
# SSH DOMAIN EXCEPTIONS
# ============================================================================


class SSHEngineError(VPSManagerError):
    """Base exception for all network and SSH protocol errors."""


class SSHAuthenticationError(SSHEngineError):
    """Raised when SSH credentials or public key exchange are rejected."""


class SSHConnectionTimeoutError(SSHEngineError):
    """Raised when socket connection or protocol handshake exceeds timeout."""


class SSHHostKeyError(SSHEngineError):
    """Raised when remote host key verification detects a mismatch."""


# ============================================================================
# METRIC EXTRACTION SCRIPT (POSIX & KERNEL DIRECT)
# ============================================================================

# POSIX-compliant script that dumps raw kernel metrics without external utility dependencies
_METRIC_PROBE_SCRIPT: Final[str] = """
set +e
echo "===VPSMAN_START==="
echo "HOSTNAME: $(uname -n 2>/dev/null || hostname)"
echo "KERNEL: $(uname -r 2>/dev/null)"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "OS: ${PRETTY_NAME:-$NAME}"
else
    echo "OS: $(uname -s 2>/dev/null)"
fi
echo "UPTIME: $(cat /proc/uptime 2>/dev/null | cut -d' ' -f1)"
echo "LOAD: $(cat /proc/loadavg 2>/dev/null | cut -d' ' -f1-3)"
echo "CPUS: $(grep -c '^processor' /proc/cpuinfo 2>/dev/null || nproc 2>/dev/null || echo 1)"
echo "---MEMINFO---"
cat /proc/meminfo 2>/dev/null | grep -E '^(MemTotal|MemFree|MemAvailable|Buffers|Cached):'
echo "---DF---"
df -Pk / 2>/dev/null | tail -n 1
echo "===VPSMAN_END==="
""".strip()


# ============================================================================
# ASYNCHRONOUS SSH SERVICE
# ============================================================================


class SSHService:
    """Enterprise SSH connection orchestrator, telemetry prober, and command runner."""

    @staticmethod
    async def measure_tcp_latency(host: str, port: int, timeout: float = 3.0) -> float | None:
        """Measure non-blocking TCP three-way handshake duration in milliseconds.

        Returns:
            Latency in ms as a float rounded to 1 decimal, or None if unreachable.
        """
        t_start = time.monotonic()
        try:
            conn_coro = asyncio.open_connection(
                host=host,
                port=port,
                family=socket.AF_UNSPEC,
            )
            _, writer = await asyncio.wait_for(conn_coro, timeout=timeout)
            duration_ms = (time.monotonic() - t_start) * 1000.0
            writer.close()
            await writer.wait_closed()
            return round(duration_ms, 1)
        except (asyncio.TimeoutError, OSError):
            return None

    @classmethod
    @asynccontextmanager
    async def acquire_connection(
        cls,
        server: Server,
        *,
        vault: SecretVault | None = None,
        known_hosts: str | Path | None = None,
    ) -> AsyncIterator[asyncssh.SSHClientConnection]:
        """Establish and yield a cryptographically authenticated SSH connection context.

        Args:
            server: Immutable server entity containing connection parameters.
            vault: Optional secret vault to decrypt stored passwords and passphrases.
            known_hosts: Path to known_hosts file. If None, host key verification is relaxed
                         to support dynamic cloud VPS instances.
        """
        # Resolve credentials
        password: str | None = None
        if server.password:
            password = vault.decrypt(server.password) if vault else server.password

        passphrase: str | None = None
        if server.key_passphrase:
            passphrase = vault.decrypt(server.key_passphrase) if vault else server.key_passphrase

        client_keys: list[str] | None = None
        if server.auth_type == AuthType.KEY_FILE and server.key_path:
            validated_path = SSHKeyValidator.validate_key_file(server.key_path)
            client_keys = [str(validated_path)]

        # Prepare asyncssh client options
        known_hosts_target: object = known_hosts if known_hosts is not None else ()

        try:
            conn_coro = asyncssh.connect(
                host=server.host,
                port=server.port,
                username=server.user,
                password=password,
                client_keys=client_keys,
                passphrase=passphrase,
                known_hosts=known_hosts_target,
                login_timeout=server.connect_timeout,
                connect_timeout=server.connect_timeout,
                agent_path=None if server.auth_type != AuthType.AGENT else cast(str, None),
            )
            async with conn_coro as conn:
                yield conn

        except asyncssh.PermissionDenied as exc:
            raise SSHAuthenticationError(
                f"Authentication failed for {server.user}@{server.host}:{server.port}: {exc}"
            ) from exc
        except (asyncio.TimeoutError, asyncssh.TimeoutError) as exc:
            raise SSHConnectionTimeoutError(
                f"Connection timed out after {server.connect_timeout}s to {server.host}:{server.port}"
            ) from exc
        except asyncssh.HostKeyNotVerifiable as exc:
            raise SSHHostKeyError(f"Host key mismatch for {server.host}: {exc}") from exc
        except (OSError, asyncssh.Error) as exc:
            raise SSHEngineError(f"SSH protocol connection error: {exc}") from exc

    @classmethod
    async def probe_server_health(
        cls,
        server: Server,
        *,
        vault: SecretVault | None = None,
        fetch_metrics: bool = True,
    ) -> Server:
        """Perform non-blocking health check and return an updated immutable Server instance.

        Executes TCP latency probe first. If reachable and fetch_metrics=True, connects
        over SSH to harvest real-time OS telemetry.
        """
        latency = await cls.measure_tcp_latency(server.host, server.port, timeout=server.connect_timeout)
        if latency is None:
            return server.with_status(status=ServerStatus.OFFLINE, latency_ms=None)

        if not fetch_metrics:
            return server.with_status(status=ServerStatus.ONLINE, latency_ms=latency)

        try:
            metrics = await cls.harvest_system_metrics(server, vault=vault)
            return server.with_status(
                status=ServerStatus.ONLINE,
                latency_ms=latency,
                metrics=metrics,
            )
        except SSHAuthenticationError:
            return server.with_status(
                status=ServerStatus.AUTH_FAILED,
                latency_ms=latency,
            )
        except SSHConnectionTimeoutError:
            return server.with_status(
                status=ServerStatus.TIMEOUT,
                latency_ms=latency,
            )
        except SSHEngineError:
            return server.with_status(
                status=ServerStatus.ERROR,
                latency_ms=latency,
            )

    @classmethod
    async def execute_command(
        cls,
        server: Server,
        command: str,
        *,
        timeout: float = 30.0,
        vault: SecretVault | None = None,
    ) -> CommandResult:
        """Execute a remote shell command asynchronously and return frozen CommandResult."""
        t_start = time.monotonic()
        try:
            async with cls.acquire_connection(server, vault=vault) as conn:
                result = await conn.run(command, check=False, timeout=timeout)
                duration = time.monotonic() - t_start

                stdout_str = cast(str, result.stdout) if isinstance(result.stdout, str) else ""
                stderr_str = cast(str, result.stderr) if isinstance(result.stderr, str) else ""

                return CommandResult(
                    server_alias=server.alias,
                    command=command,
                    exit_code=result.exit_status if result.exit_status is not None else -1,
                    stdout=stdout_str,
                    stderr=stderr_str,
                    duration_seconds=round(duration, 3),
                )

        except (asyncio.TimeoutError, asyncssh.TimeoutError):
            duration = time.monotonic() - t_start
            return CommandResult(
                server_alias=server.alias,
                command=command,
                exit_code=-99,
                stdout="",
                stderr=f"Execution timed out after {timeout:.1f} seconds.",
                duration_seconds=round(duration, 3),
            )
        except SSHEngineError as exc:
            duration = time.monotonic() - t_start
            return CommandResult(
                server_alias=server.alias,
                command=command,
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                duration_seconds=round(duration, 3),
            )

    @classmethod
    async def execute_command_streaming(
        cls,
        server: Server,
        command: str,
        *,
        timeout: float = 60.0,
        vault: SecretVault | None = None,
    ) -> AsyncIterator[tuple[str, str]]:
        """Execute remote command and stream stdout/stderr chunks in real-time as they arrive.

        Yields:
            Tuples of (stream_name, text_chunk) where stream_name is 'stdout' or 'stderr'.
        """
        async with cls.acquire_connection(server, vault=vault) as conn:
            async with conn.create_process(command) as process:
                stdout_stream = process.stdout
                stderr_stream = process.stderr

                async def _stream_reader(
                    reader: asyncssh.SSHReader[str],
                    stream_name: str,
                    queue: asyncio.Queue[tuple[str, str] | None],
                ) -> None:
                    try:
                        while True:
                            chunk = await reader.read(4096)
                            if not chunk:
                                break
                            await queue.put((stream_name, chunk))
                    finally:
                        await queue.put(None)

                queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue(maxsize=128)
                tasks = [
                    asyncio.create_task(_stream_reader(stdout_stream, "stdout", queue)),
                    asyncio.create_task(_stream_reader(stderr_stream, "stderr", queue)),
                ]

                finished_count = 0
                try:
                    while finished_count < 2:
                        item = await asyncio.wait_for(queue.get(), timeout=timeout)
                        if item is None:
                            finished_count += 1
                        else:
                            yield item
                finally:
                    for task in tasks:
                        task.cancel()
                    await process.wait()

    @classmethod
    async def execute_batch(
        cls,
        servers: Sequence[Server],
        command: str,
        *,
        max_concurrency: int = 10,
        timeout: float = 30.0,
        vault: SecretVault | None = None,
    ) -> BatchExecutionSummary:
        """Execute command across multiple servers in parallel bounded by a semaphore."""
        t_start = time.monotonic()
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _bounded_exec(srv: Server) -> CommandResult:
            async with semaphore:
                return await cls.execute_command(srv, command, timeout=timeout, vault=vault)

        tasks = [_bounded_exec(server) for server in servers]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        total_duration = time.monotonic() - t_start

        return BatchExecutionSummary.from_results(
            command=command,
            results=results,
            total_duration=total_duration,
        )

    @classmethod
    async def harvest_system_metrics(
        cls,
        server: Server,
        *,
        vault: SecretVault | None = None,
        timeout: float = 12.0,
    ) -> SystemMetrics:
        """Harvest, parse, and structure kernel performance telemetry from a Linux host."""
        res = await cls.execute_command(server, _METRIC_PROBE_SCRIPT, timeout=timeout, vault=vault)
        if not res.success:
            raise SSHEngineError(f"Metrics collection script failed (exit {res.exit_code}): {res.stderr}")

        return cls._parse_metric_payload(res.stdout)

    @classmethod
    def _parse_metric_payload(cls, raw_output: str) -> SystemMetrics:
        """Parse structured probe output into verified SystemMetrics instance."""
        data: dict[str, str] = {}
        meminfo: dict[str, int] = {}
        df_line: str = ""

        mode: str = "KV"
        for line in raw_output.splitlines():
            line = line.strip()
            if not line or line == "===VPSMAN_START===":
                continue
            if line == "---MEMINFO---":
                mode = "MEM"
                continue
            if line == "---DF---":
                mode = "DF"
                continue
            if line == "===VPSMAN_END===":
                break

            if mode == "KV":
                if ":" in line:
                    k, v = line.split(":", 1)
                    data[k.strip()] = v.strip()
            elif mode == "MEM":
                if ":" in line:
                    k, v = line.split(":", 1)
                    # Extract numeric value in kB
                    match = re.search(r"(\d+)", v)
                    if match:
                        meminfo[k.strip()] = int(match.group(1)) * 1024  # Convert KiB to Bytes
            elif mode == "DF":
                df_line = line

        # 1. Parse Uptime
        uptime_sec = 0.0
        try:
            uptime_sec = float(data.get("UPTIME", "0.0"))
        except ValueError:
            pass

        # Human formatted uptime
        days = int(uptime_sec // 86400)
        hours = int((uptime_sec % 86400) // 3600)
        minutes = int((uptime_sec % 3600) // 60)
        uptime_human = f"{days}d {hours}h {minutes}m" if days > 0 else f"{hours}h {minutes}m"

        # 2. Parse Load
        load_parts = data.get("LOAD", "0.0 0.0 0.0").split()
        load_1m = float(load_parts[0]) if len(load_parts) > 0 else 0.0
        load_5m = float(load_parts[1]) if len(load_parts) > 1 else 0.0
        load_15m = float(load_parts[2]) if len(load_parts) > 2 else 0.0

        # 3. Parse CPUs
        cpu_count = 1
        try:
            cpu_count = max(1, int(data.get("CPUS", "1")))
        except ValueError:
            pass

        # Calculate estimated CPU utilization from 1-min load average vs cores
        cpu_usage_pct = min(100.0, round((load_1m / float(cpu_count)) * 100.0, 1))

        # 4. Parse Memory
        total_mem = meminfo.get("MemTotal", 0)
        avail_mem = meminfo.get("MemAvailable", 0)
        if avail_mem == 0:
            free_mem = meminfo.get("MemFree", 0)
            buffers = meminfo.get("Buffers", 0)
            cached = meminfo.get("Cached", 0)
            avail_mem = free_mem + buffers + cached

        used_mem = max(0, total_mem - avail_mem)
        mem_pct = round((used_mem / total_mem * 100.0), 1) if total_mem > 0 else 0.0

        # 5. Parse Disk
        disk_total = 0
        disk_used = 0
        disk_free = 0
        disk_pct = 0.0

        if df_line:
            parts = df_line.split()
            # Standard df -P format: Filesystem 1024-blocks Used Available Capacity Mounted on
            if len(parts) >= 5:
                try:
                    disk_total = int(parts[1]) * 1024
                    disk_used = int(parts[2]) * 1024
                    disk_free = int(parts[3]) * 1024
                    pct_str = parts[4].rstrip("%")
                    disk_pct = float(pct_str)
                except (ValueError, IndexError):
                    pass

        return SystemMetrics(
            hostname=data.get("HOSTNAME", "unknown"),
            os_name=data.get("OS", "Linux"),
            kernel=data.get("KERNEL", "unknown"),
            uptime_seconds=uptime_sec,
            uptime_human=uptime_human,
            load_1m=load_1m,
            load_5m=load_5m,
            load_15m=load_15m,
            cpu_count=cpu_count,
            cpu_usage_pct=cpu_usage_pct,
            mem_total_bytes=total_mem,
            mem_used_bytes=used_mem,
            mem_free_bytes=avail_mem,
            mem_usage_pct=mem_pct,
            disk_total_bytes=disk_total,
            disk_used_bytes=disk_used,
            disk_free_bytes=disk_free,
            disk_usage_pct=disk_pct,
        )

    @classmethod
    def build_native_cli_command(
        cls,
        server: Server,
        *,
        vault: SecretVault | None = None,
    ) -> list[str]:
        """Build OpenSSH CLI invocation arguments for interactive terminal takeover.

        Used when suspending the Textual TUI to attach a full interactive pty session
        to the user's native terminal emulator.
        """
        cmd: list[str] = [
            "ssh",
            "-p",
            str(server.port),
            "-o",
            f"ConnectTimeout={int(server.connect_timeout)}",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
        ]

        if server.auth_type == AuthType.KEY_FILE and server.key_path:
            cmd.extend(["-i", str(Path(server.key_path).expanduser().resolve())])

        cmd.append(f"{server.user}@{server.host}")
        return cmd
