from asyncio import subprocess
import os
import sys
import json
import getpass
from concurrent.futures import ThreadPoolExecutor
from vps_manager.config import CONFIG_FILE, CLR_RESET, CLR_BOLD, CLR_RED, CLR_GREEN, CLR_YELLOW, CLR_BLUE, CLR_CYAN, init_storage
from vps_manager.models import Server
from vps_manager.ssh import SSHService


class VPSManagerApp:
    def __init__(self):
        init_storage()
        self.servers = []
        self.load_servers()

    def load_servers(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.servers = [Server.from_dict(item) for item in data]
        except Exception:
            self.servers = []

    def save_servers(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in self.servers], f, indent=4)

    def clear(self):
        os.system("clear")

    def header(self, title: str):
        width = 65
        print(f"\n{CLR_BLUE}{'=' * width}{CLR_RESET}")
        print(f"{CLR_BOLD}{CLR_CYAN}{title.center(width)}{CLR_RESET}")
        print(f"{CLR_BLUE}{'=' * width}{CLR_RESET}\n")

    def prompt(self, text: str, default: str = "", secret: bool = False) -> str:
        placeholder = f" [{default}]" if default and not secret else ""
        try:
            if secret:
                val = getpass.getpass(f"{CLR_BOLD}{text}{CLR_RESET}: ").strip()
            else:
                val = input(f"{CLR_BOLD}{text}{placeholder}{CLR_RESET}: ").strip()
            return val if val else default
        except KeyboardInterrupt:
            print(f"\n{CLR_YELLOW}[!] Input dibatalkan.{CLR_RESET}")
            return ""

    def list_servers_table(self, check_status: bool = False):
        self.clear()
        self.header("DAFTAR SERVER" if not check_status else "DAFTAR SERVER + CEK STATUS")

        if not self.servers:
            print(f"{CLR_YELLOW}Belum ada server yang terdaftar.{CLR_RESET}")
            return False

        statuses = {}
        if check_status:
            print(f"{CLR_YELLOW}Memeriksa koneksi ke semua VPS secara paralel...{CLR_RESET}\n")
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(SSHService.check_connection, s): s.alias for s in self.servers}
                for fut in futures:
                    alias = futures[fut]
                    try:
                        statuses[alias] = fut.result()
                    except Exception:
                        statuses[alias] = False

        print(f"{CLR_BOLD}{'No.':<4} {'Alias':<15} {'User@Host:Port':<28} {'Auth':<10} {'Status/Deskripsi':<15}{CLR_RESET}")
        print(f"{CLR_BLUE}{'-' * 70}{CLR_RESET}")

        for idx, srv in enumerate(self.servers, 1):
            conn = f"{srv.user}@{srv.host}:{srv.port}"
            auth_lbl = "🔑 Key" if srv.auth_type == "key" else "🔒 Pass"
            
            if check_status:
                is_up = statuses.get(srv.alias, False)
                extra = f"{CLR_GREEN}ONLINE{CLR_RESET}" if is_up else f"{CLR_RED}OFFLINE{CLR_RESET}"
            else:
                extra = srv.description[:18] if srv.description else "-"

            print(f"{idx:<4} {CLR_CYAN}{srv.alias:<15}{CLR_RESET} {conn:<28} {auth_lbl:<10} {extra}")
        print(f"{CLR_BLUE}{'-' * 70}{CLR_RESET}")
        return True

    def menu_add_server(self):
        self.clear()
        self.header("TAMBAH SERVER")
        
        alias = self.prompt("Alias Server (Harus Unik)")
        if not alias: return
        if any(s.alias.lower() == alias.lower() for s in self.servers):
            print(f"{CLR_RED}[!] Alias '{alias}' sudah terdaftar!{CLR_RESET}")
            input("\nTekan Enter..."); return

        host = self.prompt("Host / IP Address VPS")
        if not host: return

        user = self.prompt("SSH Username", default="root")
        if not user: return

        port_str = self.prompt("SSH Port", default="22")
        try:
            port = int(port_str)
        except ValueError:
            print(f"{CLR_RED}[!] Port harus berupa angka!{CLR_RESET}")
            input("\nTekan Enter..."); return

        print(f"\n{CLR_BOLD}Tipe Autentikasi:{CLR_RESET}")
        print("1. SSH Keyfile (Direkomendasikan)")
        print("2. Password VPS")
        auth_choice = self.prompt("Pilih Metode (1-2)", default="1")

        auth_type = "key"
        password = None
        key_path = None

        if auth_choice == "2":
            auth_type = "password"
            password = self.prompt("Masukkan Password VPS (Input Tersembunyi)", secret=True)
            if not password:
                print(f"{CLR_RED}[!] Password tidak boleh kosong jika memilih tipe password!{CLR_RESET}")
                input("\nTekan Enter..."); return
        else:
            key_path = self.prompt("Path ke SSH Keyfile", default="~/.ssh/id_rsa")

        desc = self.prompt("Deskripsi VPS (Opsional)")

        new_server = Server(
            alias=alias, host=host, user=user, port=port,
            auth_type=auth_type, password=password, key_path=key_path, description=desc
        )
        self.servers.append(new_server)
        self.save_servers()
        
        print(f"\n{CLR_GREEN}[✓] Server '{alias}' berhasil ditambahkan!{CLR_RESET}")
        input("\nTekan Enter untuk kembali...")

    def menu_remove_server(self):
        if not self.list_servers_table(check_status=False):
            input("\nTekan Enter..."); return

        alias = self.prompt("\nMasukkan Alias server yang ingin dihapus")
        if not alias: return

        found = any(s.alias.lower() == alias.lower() for s in self.servers)
        if not found:
            print(f"{CLR_RED}[!] Server dengan alias '{alias}' tidak ditemukan.{CLR_RESET}")
            input("\nTekan Enter..."); return

        confirm = self.prompt(f"Yakin ingin menghapus '{alias}'? (y/N)", default="n").lower()
        if confirm == "y":
            self.servers = [s for s in self.servers if s.alias.lower() != alias.lower()]
            self.save_servers()
            print(f"{CLR_GREEN}[✓] Server berhasil dihapus!{CLR_RESET}")
        input("\nTekan Enter...")

    def menu_connect_ssh(self):
        if not self.list_servers_table(check_status=False):
            input("\nTekan Enter..."); return

        target = self.prompt("\nMasukkan Nomor atau Alias Server target")
        if not target: return

        selected = None
        if target.isdigit():
            idx = int(target) - 1
            if 0 <= idx < len(self.servers):
                selected = self.servers[idx]
        else:
            for s in self.servers:
                if s.alias.lower() == target.lower():
                    selected = s
                    break

        if not selected:
            print(f"{CLR_RED}[!] Server target tidak ditemukan.{CLR_RESET}")
            input("\nTekan Enter..."); return

        if selected.auth_type == "password" and not SSHService.is_sshpass_installed():
            print(f"\n{CLR_YELLOW}[⚠️] Peringatan: Paket 'sshpass' belum terpasang.")
            print(f"Sistem akan dialihkan ke autentikasi interaktif manual.{CLR_RESET}")
            selected = Server(
                alias=selected.alias, host=selected.host, user=selected.user,
                port=selected.port, auth_type="password", password=None, description=selected.description
            )

        try:
            cmd = SSHService.build_ssh_command(selected, interactive=True)
            self.clear()
            print(f"{CLR_GREEN}[*] Menghubungkan ke {selected.alias}...{CLR_RESET}")
            subprocess.run(cmd)
        except Exception as e:
            print(f"{CLR_RED}[!] Error koneksi: {e}{CLR_RESET}")
        
        print(f"\n{CLR_YELLOW}[*] Sesi SSH diakhiri.{CLR_RESET}")
        input("\nTekan Enter...")

    def menu_execute_command(self):
        if not self.servers:
            print(f"{CLR_YELLOW}Belum ada server terdaftar.{CLR_RESET}")
            input("\nTekan Enter..."); return

        self.clear()
        self.header("EKSEKUSI PERINTAH MASSAL")
        print("1. Jalankan di SATU server")
        print("2. Jalankan di SEMUA server terdaftar")
        choice = self.prompt("Pilihan Opsi", default="1")

        targets = []
        if choice == "1":
            self.list_servers_table(check_status=False)
            target = self.prompt("\nMasukkan No/Alias Server")
            if target.isdigit():
                idx = int(target) - 1
                if 0 <= idx < len(self.servers):
                    targets.append(self.servers[idx])
            else:
                for s in self.servers:
                    if s.alias.lower() == target.lower():
                        targets.append(s)
                        break
        elif choice == "2":
            targets = self.servers

        if not targets:
            print(f"{CLR_RED}[!] Target server tidak valid!{CLR_RESET}")
            input("\nTekan Enter..."); return

        cmd = self.prompt("Masukkan perintah bash (misal: 'uname -a && uptime')")
        if not cmd: return

        print(f"\n{CLR_YELLOW}[*] Mengirim perintah ke {len(targets)} server...{CLR_RESET}\n")

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = executor.map(lambda srv: SSHService.execute_command(srv, cmd), targets)

        for alias, code, stdout, stderr in results:
            print(f"{CLR_BOLD}{CLR_CYAN}[ SERVER: {alias} ]{CLR_RESET}")
            if code == 0:
                print(f"{CLR_GREEN}[SUKSES]{CLR_RESET}")
                print(stdout.strip() if stdout.strip() else "(Tanpa output)")
            else:
                print(f"{CLR_RED}[GAGAL - Code {code}]{CLR_RESET}")
                print(stderr.strip() if stderr.strip() else "(Pesan error kosong)")
            print(f"{CLR_BLUE}{'-' * 45}{CLR_RESET}\n")

        input("\nTekan Enter...")

    def run(self):
        while True:
            try:
                self.clear()
                self.header("ARCH VPS & SSH MANAGER")
                print(f" {CLR_BOLD}1.{CLR_RESET} Tampilkan Daftar VPS")
                print(f" {CLR_BOLD}2.{CLR_RESET} Cek Status Koneksi VPS (Online/Offline)")
                print(f" {CLR_BOLD}3.{CLR_RESET} Tambah Server Baru")
                print(f" {CLR_BOLD}4.{CLR_RESET} Hapus Server")
                print(f" {CLR_BOLD}5.{CLR_RESET} Koneksi SSH Cepat (Auto-Login)")
                print(f" {CLR_BOLD}6.{CLR_RESET} Jalankan Perintah Massal (Multi-exec)")
                print(f" {CLR_BOLD}0.{CLR_RESET} Keluar Aplikasi")
                print(f"\n{CLR_BLUE}{'=' * 65}{CLR_RESET}")
                
                choice = self.prompt("Pilih Opsi [0-6]", default="1")

                if choice == "1":
                    self.list_servers_table(check_status=False)
                    input("\nTekan Enter untuk kembali...")
                elif choice == "2":
                    self.list_servers_table(check_status=True)
                    input("\nTekan Enter untuk kembali...")
                elif choice == "3":
                    self.menu_add_server()
                elif choice == "4":
                    self.menu_remove_server()
                elif choice == "5":
                    self.menu_connect_ssh()
                elif choice == "6":
                    self.menu_execute_command()
                elif choice == "0":
                    print(f"\n{CLR_GREEN}Selamat tinggal!{CLR_RESET}")
                    break
            except KeyboardInterrupt:
                print(f"\n\n{CLR_GREEN}Sampai jumpa!{CLR_RESET}")
                sys.exit(0)
