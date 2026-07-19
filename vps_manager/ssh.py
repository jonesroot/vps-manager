import os
import shutil
import asyncio
from typing import Tuple, List, Dict, Any, Optional
from vps_manager.models import Server

class SSHService:
    @staticmethod
    def is_sshpass_installed() -> bool:
        """Memeriksa keberadaan biner pelengkap sshpass pada sistem induk."""
        return shutil.which("sshpass") is not None

    @staticmethod
    async def check_connection(server: Server, timeout: float = 2.5) -> bool:
        """Memverifikasi ketersediaan port TCP SSH target secara asinkron."""
        try:
            conn = asyncio.open_connection(server.host, server.port)
            _, writer = await asyncio.wait_for(conn, timeout=timeout)
            writer.close()
            await writer.wait_closed()
            return True
        except (asyncio.TimeoutError, OSError):
            return False

    @classmethod
    def build_ssh_command(cls, server: Server, interactive: bool = True, command: str = "") -> List[str]:
        """Merakit argumen biner SSH dengan optimasi keamanan enkripsi terenkapsulasi."""
        ssh_cmd = [
            "ssh",
            "-p", str(server.port),
            "-o", "ConnectTimeout=8",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null"
        ]

        if not interactive:
            ssh_cmd.extend(["-o", "BatchMode=yes"])

        if server.auth_type == "key" and server.key_path:
            expanded_path = os.path.expanduser(server.key_path)
            ssh_cmd.extend(["-i", expanded_path])

        ssh_cmd.append(f"{server.user}@{server.host}")

        if command:
            ssh_cmd.append(command)

        if server.auth_type == "password" and server.password:
            if cls.is_sshpass_installed():
                ssh_cmd = ["sshpass", "-p", server.password] + ssh_cmd
            elif not interactive:
                raise RuntimeError("Modul 'sshpass' tidak terdeteksi untuk integrasi sandi otomatis.")

        return ssh_cmd

    @classmethod
    async def execute_command_async(cls, server: Server, command: str, timeout: float = 20.0) -> Tuple[str, int, str, str]:
        """Mengeksekusi instruksi jarak jauh secara asinkron (Paralel Non-Blocking)."""
        try:
            cmd_args = cls.build_ssh_command(server, interactive=False, command=command)
            
            process = await asyncio.create_subprocess_exec(
                cmd_args[0], *cmd_args[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                return (
                    server.alias,
                    process.returncode if process.returncode is not None else -1,
                    stdout.decode('utf-8', errors='replace'),
                    stderr.decode('utf-8', errors='replace')
                )
            except asyncio.TimeoutError:
                try:
                    process.terminate()
                except OSError:
                    pass
                return server.alias, -99, "", f"Waktu eksekusi terlampaui (Batas waktu: {timeout} detik)."
        except Exception as e:
            return server.alias, -1, "", str(e)

    @classmethod
    async def fetch_vitals_async(cls, server: Server) -> Dict[str, Any]:
        """Mengambil data telemetri vitalitas server jarak jauh secara paralel (Real-time)."""
        vitals_cmd = (
            "echo '===METRICS===' && "
            "echo \"OS: $(uname -s)\" && "
            "echo \"LOAD: $(cat /proc/loadavg 2>/dev/null | awk '{print $1}' || uptime | awk -F'load average:' '{print $2}' | sed 's/^[ \\t]*//' | cut -d',' -f1 || echo '0.00')\" && "
            "echo \"RAM: $(free -m 2>/dev/null | awk '/Mem:/ {print $3\"_\"$2}' || cat /proc/meminfo 2>/dev/null | awk '/MemTotal/ {t=$2} /MemAvailable/ {a=$2} END {print int((t-a)/1024)\"_\"int(t/1024)}' || echo '0_0')\" && "
            "echo \"DISK: $(df -Ph / 2>/dev/null | awk 'NR==2 {print $3\"_\"$2\"_\"$5}' || echo '0_0_0%')\" && "
            "echo '===END_METRICS==='"
        )
        
        is_online = await cls.check_connection(server, timeout=2.0)
        if not is_online:
            return {"status": "OFFLINE", "cpu": "N/A", "ram": "N/A", "disk": "N/A", "os": "Unknown"}

        alias, code, stdout, stderr = await cls.execute_command_async(server, vitals_cmd, timeout=5.0)
        
        metrics = {
            "status": "ONLINE",
            "os": "N/A",
            "cpu": "N/A",
            "ram": "N/A",
            "disk": "N/A"
        }

        if code == 0:
            try:
                stdout_lines = stdout.splitlines()
                inside_metrics = False
                metric_lines = []
                
                for line in stdout_lines:
                    line_str = line.strip()
                    if line_str == "===METRICS===":
                        inside_metrics = True
                        continue
                    elif line_str == "===END_METRICS===":
                        inside_metrics = False
                        continue
                    if inside_metrics:
                        metric_lines.append(line_str)

                for line in metric_lines:
                    if line.startswith("OS:"):
                        metrics["os"] = line.replace("OS:", "").strip()
                    elif line.startswith("LOAD:"):
                        load_val = line.replace("LOAD:", "").strip()
                        if load_val:
                            metrics["cpu"] = load_val.split(',')[0].strip()
                    elif line.startswith("RAM:"):
                        ram_val = line.replace("RAM:", "").strip()
                        try:
                            used, total = ram_val.split('_')
                            used_f = float(used)
                            total_f = float(total)
                            if total_f > 0:
                                if total_f > 1500:
                                    metrics["ram"] = f"{used_f/1024:.1f}/{total_f/1024:.1f} GB"
                                else:
                                    metrics["ram"] = f"{used_f:.0f}/{total_f:.0f} MB"
                            else:
                                metrics["ram"] = "N/A"
                        except Exception:
                            metrics["ram"] = "N/A"
                    elif line.startswith("DISK:"):
                        disk_val = line.replace("DISK:", "").strip()
                        try:
                            parts = disk_val.split('_')
                            if len(parts) >= 3:
                                metrics["disk"] = f"{parts[0]}/{parts[1]} ({parts[2]})"
                            else:
                                metrics["disk"] = "N/A"
                        except Exception:
                            metrics["disk"] = "N/A"
            except Exception:
                pass
        
        return metrics
