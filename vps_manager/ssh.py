# vps_manager/ssh.py
import asyncio
import shutil
import os
import time
from typing import Tuple, List
from vps_manager.models import Server, CommandResult


class SSHService:

    @staticmethod
    def is_sshpass_installed() -> bool:
        return shutil.which("sshpass") is not None

    @staticmethod
    async def check_connection(server: Server, timeout: float = 3.0) -> bool:
        """Ping TCP ke port SSH server secara asinkron."""
        try:
            conn = asyncio.open_connection(server.host, server.port)
            _, writer = await asyncio.wait_for(conn, timeout=timeout)
            writer.close()
            await writer.wait_closed()
            return True
        except (asyncio.TimeoutError, OSError):
            return False

    @staticmethod
    async def check_latency(server: Server, timeout: float = 5.0) -> float:
        """Ukur latensi TCP ke server dalam milidetik. Return -1.0 jika gagal."""
        try:
            t0 = time.monotonic()
            conn = asyncio.open_connection(server.host, server.port)
            _, writer = await asyncio.wait_for(conn, timeout=timeout)
            latency = (time.monotonic() - t0) * 1000
            writer.close()
            await writer.wait_closed()
            return round(latency, 1)
        except (asyncio.TimeoutError, OSError):
            return -1.0

    @classmethod
    def build_ssh_command(
        cls,
        server: Server,
        interactive: bool = True,
        command: str = "",
        extra_opts: List[str] = None
    ) -> List[str]:
        """Bangun argumen perintah SSH."""
        ssh_cmd: List[str] = [
            "ssh",
            "-p", str(server.port),
            "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
        ]

        if not interactive:
            ssh_cmd.extend([
                "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR",
            ])

        if extra_opts:
            for opt in extra_opts:
                ssh_cmd.extend(["-o", opt])

        if server.auth_type == "key" and server.key_path:
            expanded = os.path.expanduser(server.key_path)
            ssh_cmd.extend(["-i", expanded])

        ssh_cmd.append(f"{server.user}@{server.host}")

        if command:
            ssh_cmd.append(command)

        if server.auth_type == "password" and server.password:
            if cls.is_sshpass_installed():
                ssh_cmd = ["sshpass", "-p", server.password] + ssh_cmd
            elif not interactive:
                raise RuntimeError("Paket 'sshpass' diperlukan untuk auto-login berbasis password.")

        return ssh_cmd

    @classmethod
    async def execute_command_async(
        cls,
        server: Server,
        command: str,
        timeout: float = 25.0
    ) -> CommandResult:
        """Eksekusi perintah shell secara asinkron dan kembalikan CommandResult."""
        t_start = time.monotonic()
        try:
            cmd_args = cls.build_ssh_command(server, interactive=False, command=command)

            process = await asyncio.create_subprocess_exec(
                cmd_args[0], *cmd_args[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                duration = time.monotonic() - t_start
                return CommandResult(
                    alias     = server.alias,
                    exit_code = process.returncode if process.returncode is not None else -1,
                    stdout    = stdout.decode('utf-8', errors='replace'),
                    stderr    = stderr.decode('utf-8', errors='replace'),
                    duration  = round(duration, 2),
                )
            except asyncio.TimeoutError:
                try:
                    process.terminate()
                except OSError:
                    pass
                return CommandResult(
                    alias     = server.alias,
                    exit_code = -99,
                    stdout    = "",
                    stderr    = f"Timeout: eksekusi melebihi {timeout:.0f} detik",
                    duration  = timeout,
                )
        except Exception as exc:
            return CommandResult(
                alias     = server.alias,
                exit_code = -1,
                stdout    = "",
                stderr    = str(exc),
                duration  = time.monotonic() - t_start,
            )

    @classmethod
    async def get_server_info(cls, server: Server) -> dict:
        """Ambil ringkasan info sistem (uptime, load, mem, OS) dari server."""
        cmd = (
            "echo '===VPSMAN_INFO==='; "
            "uname -sr 2>/dev/null; "
            "uptime -p 2>/dev/null || uptime; "
            "free -h 2>/dev/null | awk 'NR==2{print \"MEM:\", $2, $3, $4}'; "
            "df -h / 2>/dev/null | awk 'NR==2{print \"DISK:\", $2, $3, $4, $5}'; "
            "echo 'LOAD:' $(cat /proc/loadavg 2>/dev/null | cut -d' ' -f1-3)"
        )
        result = await cls.execute_command_async(server, cmd, timeout=10.0)
        info = {
            "os": "N/A", "uptime": "N/A",
            "mem_total": "N/A", "mem_used": "N/A", "mem_free": "N/A",
            "disk_total": "N/A", "disk_used": "N/A", "disk_avail": "N/A", "disk_pct": "N/A",
            "load": "N/A",
            "success": result.success,
        }
        if not result.success:
            return info
        for line in result.stdout.splitlines():
            if line.startswith("MEM:"):
                parts = line.split()
                if len(parts) >= 4:
                    info.update(mem_total=parts[1], mem_used=parts[2], mem_free=parts[3])
            elif line.startswith("DISK:"):
                parts = line.split()
                if len(parts) >= 5:
                    info.update(disk_total=parts[1], disk_used=parts[2], disk_avail=parts[3], disk_pct=parts[4])
            elif line.startswith("LOAD:"):
                info["load"] = line.replace("LOAD:", "").strip()
            elif line.startswith("up "):
                info["uptime"] = line.strip()
            elif line and not line.startswith("==="):
                info["os"] = line.strip()
        return info
