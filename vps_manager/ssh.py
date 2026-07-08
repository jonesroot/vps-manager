import os
import shutil
import socket
import subprocess
from typing import List, Tuple
from vps_manager.models import Server


class SSHService:
    @staticmethod
    def is_sshpass_installed() -> bool:
        return shutil.which("sshpass") is not None

    @staticmethod
    def check_connection(server: Server, timeout: float = 2.0) -> bool:
        try:
            with socket.create_connection((server.host, server.port), timeout=timeout):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    @classmethod
    def build_ssh_command(cls, server: Server, interactive: bool = True, command: str = "") -> List[str]:
        ssh_cmd = ["ssh", "-p", str(server.port)]
        
        if not interactive:
            ssh_cmd.extend([
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=5",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null"
            ])

        # Penanganan SSH Key
        if server.auth_type == "key" and server.key_path:
            ssh_cmd.extend(["-i", os.path.expanduser(server.key_path)])

        ssh_cmd.append(f"{server.user}@{server.host}")

        if command:
            ssh_cmd.append(command)

        # Penanganan Password menggunakan sshpass
        if server.auth_type == "password" and server.password:
            if cls.is_sshpass_installed():
                ssh_cmd = ["sshpass", "-p", server.password] + ssh_cmd
            elif not interactive:
                raise RuntimeError("Membutuhkan 'sshpass' untuk autentikasi password otomatis.")

        return ssh_cmd

    @classmethod
    def execute_command(cls, server: Server, command: str) -> Tuple[str, int, str, str]:
        try:
            cmd = cls.build_ssh_command(server, interactive=False, command=command)
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
            return server.alias, res.returncode, res.stdout, res.stderr
        except subprocess.TimeoutExpired:
            return server.alias, -99, "", "Koneksi Timeout (15s)"
        except Exception as e:
            return server.alias, -1, "", str(e)
