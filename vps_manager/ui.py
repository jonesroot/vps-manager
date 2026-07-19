import os
import sys
import json
import getpass
import asyncio
import subprocess
from typing import List, Optional, Dict, Any

from vps_manager.config import (
    CONFIG_FILE, SNIPPET_FILE, init_storage, get_terminal_width,
    CLR_RESET, CLR_BOLD, CLR_DIM, CLR_RED, CLR_GREEN, CLR_YELLOW, CLR_BLUE, CLR_PURPLE, CLR_CYAN, CLR_GRAY,
    B_TL, B_TR, B_BL, B_BR, B_H, B_V, B_L_DIV, B_R_DIV,
    ICON_KEY, ICON_PASS, ICON_ONLINE, ICON_OFFLINE, ICON_SUCCESS, ICON_WARN, ICON_TAG,
    ICON_CPU, ICON_RAM, ICON_DISK, ICON_UPTIME, RESET
)
from vps_manager.models import Server, Snippet
from vps_manager.ssh import SSHService


class VPSManagerApp:
    def __init__(self):
        init_storage()
        self.servers: List[Server] = []
        self.snippets: List[Snippet] = []
        self.load_data()

    def load_data(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                self.servers = [Server.from_dict(item) for item in json.load(f)]
        except Exception:
            self.servers = []

        try:
            with open(SNIPPET_FILE, "r", encoding="utf-8") as f:
                self.snippets = [Snippet.from_dict(item) for item in json.load(f)]
        except Exception:
            self.snippets = []

    def save_servers(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump([s.to_dict() for s in self.servers], f, indent=4)
        except Exception as e:
            self.draw_box("DATABASE ERROR", [f"Gagal menyimpan server: {e}"], CLR_RED)

    def save_snippets(self):
        try:
            with open(SNIPPET_FILE, "w", encoding="utf-8") as f:
                json.dump([sn.to_dict() for sn in self.snippets], f, indent=4)
        except Exception as e:
            self.draw_box("DATABASE ERROR", [f"Gagal menyimpan snippet: {e}"], CLR_RED)

    def clear(self):
        os.system("clear" if os.name != "nt" else "cls")

    def get_layout_width(self) -> int:
        width = get_terminal_width() - 4
        return max(75, min(width, 105))

    def draw_box(self, title: str, lines: List[str], color: str = CLR_PURPLE):
        width = self.get_layout_width()
        print(f"{color}{B_TL}{B_H * (width - 2)}{B_TR}{CLR_RESET}")
        title_padding = width - len(title) - 2
        left_pad = title_padding // 2
        right_pad = title_padding - left_pad
        print(f"{color}{B_V}{CLR_RESET}{' ' * left_pad}{CLR_BOLD}{CLR_CYAN}{title}{CLR_RESET}{' ' * right_pad}{color}{B_V}{CLR_RESET}")
        print(f"{color}{B_L_DIV}{B_H * (width - 2)}{B_R_DIV}{CLR_RESET}")
        for line in lines:
            line_content = line[:width-4]
            padding = width - len(line_content) - 4
            print(f"{color}{B_V}{CLR_RESET} {line_content}{' ' * padding} {color}{B_V}{CLR_RESET}")
        print(f"{color}{B_BL}{B_H * (width - 2)}{B_BR}{CLR_RESET}")

    def prompt(self, text: str, default: str = "", secret: bool = False) -> str:
        placeholder = f" ({default})" if default and not secret else ""
        prompt_symbol = "❯"
        try:
            if secret:
                val = getpass.getpass(f"{CLR_BOLD}{CLR_GREEN}{prompt_symbol}{CLR_RESET} {text}{placeholder}: ").strip()
            else:
                val = input(f"{CLR_BOLD}{CLR_GREEN}{prompt_symbol}{CLR_RESET} {text}{placeholder}: ").strip()
            return val if val else default
        except (KeyboardInterrupt, EOFError):
            print(f"\n{CLR_RED}[!] Operasi dibatalkan.{CLR_RESET}")
            return ""

    async def run_visual_spinner(self, message: str, task):
        """Menampilkan teks animasi pemuatan (loading spinner) sewaktu eksekusi tugas."""
        symbols = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        i = 0
        while not task.done():
            sys.stdout.write(f"\r {CLR_YELLOW}{symbols[i % len(symbols)]}{CLR_RESET} {message}")
            sys.stdout.flush()
            await asyncio.sleep(0.08)
            i += 1
        sys.stdout.write("\r" + " " * (len(message) + 4) + "\r")
        sys.stdout.flush()
        return await task

    async def list_servers_table(self, check_status: bool = False, tag_filter: str = "") -> bool:
        self.clear()
        
        banner_desc = ["Arsitektur Database Node Virtual Jaringan"]
        if tag_filter:
            banner_desc.append(f"Menyaring kategori tag: [{tag_filter}]")
            
        self.draw_box("PENGELOLA SERVER VPS", banner_desc, CLR_BLUE)

        filtered_servers = self.servers
        if tag_filter:
            filtered_servers = [s for s in self.servers if s.tags and tag_filter.lower() in [t.lower() for t in s.tags]]

        if not filtered_servers:
            print(f"\n{CLR_YELLOW} {ICON_WARN} Tidak ada server terdaftar untuk ditampilkan.{CLR_RESET}")
            return False

        width = self.get_layout_width()

        vitals_data = {}
        if check_status:
            tasks = [SSHService.fetch_vitals_async(s) for s in filtered_servers]
            wrapped_task = asyncio.ensure_future(asyncio.gather(*tasks))
            results = await self.run_visual_spinner("Menghubungkan & mengunduh status metrik server...", wrapped_task)
            for server, vitals in zip(filtered_servers, results):
                vitals_data[server.alias] = vitals

        col_no_w = 4
        col_alias_w = 12
        col_conn_w = 26
        col_auth_w = 8
        col_metric_w = width - (col_no_w + col_alias_w + col_conn_w + col_auth_w + 10)

        header = (
            f"{'ID':<{col_no_w}} "
            f"{'Alias':<{col_alias_w}} "
            f"{'Akses (User@Host:Port)':<{col_conn_w}} "
            f"{'Auth':<{col_auth_w}} "
            f"{'Metrik / Status Pemantauan':<{col_metric_w}}"
        )
        print(f"\n{CLR_BOLD}{CLR_CYAN}{header}{CLR_RESET}")
        print(f"{CLR_BLUE}{B_H * width}{CLR_RESET}")

        for idx, srv in enumerate(filtered_servers, 1):
            conn = f"{srv.user}@{srv.host}:{srv.port}"
            if len(conn) > col_conn_w:
                conn = conn[:col_conn_w - 3] + "..."

            auth_lbl = f"{ICON_KEY} Key" if srv.auth_type == "key" else f"{ICON_PASS} Pass"

            if check_status:
                data = vitals_data.get(srv.alias, {})
                if data.get("status") == "OFFLINE":
                    status_lbl = f"{CLR_RED}{ICON_OFFLINE} OFFLINE{CLR_RESET}"
                else:
                    status_lbl = (
                        f"{CLR_GREEN}{ICON_ONLINE} {data.get('os','N/A')}{CLR_RESET} | "
                        f"{CLR_CYAN}{ICON_CPU}{CLR_RESET} Load: {data.get('cpu','0')}{CLR_RESET} | "
                        f"{CLR_YELLOW}{ICON_RAM}{CLR_RESET} {data.get('ram','0')} | "
                        f"{CLR_PURPLE}{ICON_DISK}{CLR_RESET} {data.get('disk','0')}"
                    )
            else:
                tag_str = f" {ICON_TAG} {','.join(srv.tags)}" if srv.tags else ""
                desc = srv.description if srv.description else "-"
                status_lbl = f"{desc} {CLR_GRAY}{tag_str}{CLR_RESET}"

            row = (
                f"{idx:<{col_no_w}} "
                f"{CLR_BOLD}{srv.alias:<{col_alias_w}}{CLR_RESET} "
                f"{conn:<{col_conn_w}} "
                f"{auth_lbl:<{col_auth_w}} "
                f"{status_lbl}"
            )
            print(row)

        print(f"{CLR_BLUE}{B_H * width}{CLR_RESET}\n")
        return True

    def menu_add_server(self):
        self.clear()
        self.draw_box("DAFTARKAN SERVER BARU", ["Silakan isikan konfigurasi autentikasi VPS tujuan"], CLR_GREEN)

        alias = self.prompt("Alias Server (ID Unik)")
        if not alias: return
        if any(s.alias.lower() == alias.lower() for s in self.servers):
            print(f"{CLR_RED}\n[!] Error: Alias '{alias}' telah digunakan!{CLR_RESET}")
            self.prompt("Tekan [Enter] untuk kembali")
            return

        host = self.prompt("Alamat IP / Domain VPS")
        if not host: return

        user = self.prompt("Username SSH", default="root")
        if not user: return

        port_str = self.prompt("Port SSH", default="22")
        try:
            port = int(port_str)
        except ValueError:
            print(f"{CLR_RED}\n[!] Error: Port harus berupa nilai angka!{CLR_RESET}")
            self.prompt("Tekan [Enter] untuk kembali")
            return

        print(f"\n{CLR_BOLD}Metode Autentikasi Keamanan:{CLR_RESET}")
        print("  1) Kunci Privat SSH / Private Key (Disarankan)")
        print("  2) Password Sistem")
        auth_choice = self.prompt("Pilihan (1/2)", default="1")

        auth_type = "key"
        password = None
        key_path = None

        if auth_choice == "2":
            auth_type = "password"
            password = self.prompt("Sandi Akses (Tersembunyi)", secret=True)
            if not password:
                print(f"{CLR_RED}\n[!] Error: Sandi autentikasi wajib diisi!{CLR_RESET}")
                self.prompt("Tekan [Enter] untuk kembali")
                return
        else:
            key_path = self.prompt("Lokasi Kunci Privat SSH", default="~/.ssh/id_rsa")

        desc = self.prompt("Deskripsi Server")
        tags_raw = self.prompt("Tag Klasifikasi (Gunakan koma sebagai pemisah, contoh: production,db)")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        new_server = Server(
            alias=alias, host=host, user=user, port=port,
            auth_type=auth_type, password=password, key_path=key_path, description=desc, tags=tags
        )

        validation_err = new_server.validate()
        if validation_err:
            print(f"{CLR_RED}\n[!] Gagal divalidasi: {validation_err}{CLR_RESET}")
        else:
            self.servers.append(new_server)
            self.save_servers()
            print(f"\n{CLR_GREEN}{ICON_SUCCESS} Server '{alias}' terdaftar sempurna!{CLR_RESET}")

        self.prompt("Tekan [Enter] untuk kembali")

    async def menu_edit_server(self):
        if not await self.list_servers_table(check_status=False):
            self.prompt("Tekan [Enter] untuk kembali")
            return

        target = self.prompt("Pilih ID atau nama Alias server yang akan diperbarui")
        if not target: return

        selected_idx = -1
        selected: Optional[Server] = None

        if target.isdigit():
            idx = int(target) - 1
            if 0 <= idx < len(self.servers):
                selected_idx = idx
                selected = self.servers[idx]
        else:
            for i, s in enumerate(self.servers):
                if s.alias.lower() == target.lower():
                    selected_idx = i
                    selected = s
                    break

        if selected is None:
            print(f"{CLR_RED}[!] Node server tidak ditemukan.{CLR_RESET}")
            self.prompt("Tekan [Enter] untuk kembali")
            return

        self.clear()
        self.draw_box(f"UBAH METADATA NODE: {selected.alias}", ["Kosongkan pilihan untuk menggunakan data lama"], CLR_YELLOW)

        new_alias = self.prompt("Ganti Alias", default=selected.alias)
        if new_alias != selected.alias:
            if any(s.alias.lower() == new_alias.lower() for i, s in enumerate(self.servers) if i != selected_idx):
                print(f"{CLR_RED}[!] Nama alias '{new_alias}' telah dialokasikan untuk server lain!{CLR_RESET}")
                self.prompt("Tekan [Enter] untuk kembali")
                return

        new_host = self.prompt("Ganti Host/IP", default=selected.host)
        new_user = self.prompt("Ganti SSH Username", default=selected.user)
        new_port_str = self.prompt("Ganti Port SSH", default=str(selected.port))
        try:
            new_port = int(new_port_str)
        except ValueError:
            print(f"{CLR_RED}[!] Nilai port yang diisi tidak valid!")
            self.prompt("Tekan [Enter] untuk kembali")
            return

        new_auth_type = selected.auth_type
        new_password = selected.password
        new_key_path = selected.key_path

        change_auth = self.prompt("Apakah skema autentikasi ingin diganti? (y/N)", default="n").lower()
        if change_auth == 'y':
            print("\n 1) Private Key SSH\n 2) Password VPS")
            choice = self.prompt("Pilih", default="1")
            if choice == "2":
                new_auth_type = "password"
                new_password = self.prompt("Isi Sandi Baru", secret=True)
                new_key_path = None
            else:
                new_auth_type = "key"
                new_key_path = self.prompt("Isi Jalur SSH Key Baru", default="~/.ssh/id_rsa")
                new_password = None
        else:
            if selected.auth_type == "password":
                up_pass = self.prompt("Ganti kata sandi lama? (y/N)", default="n").lower()
                if up_pass == 'y':
                    new_password = self.prompt("Sandi Baru", secret=True)
            else:
                new_key_path = self.prompt("Konfigurasi jalur SSH Key", default=selected.key_path)

        new_desc = self.prompt("Modifikasi Deskripsi", default=selected.description)
        old_tags = ",".join(selected.tags) if selected.tags else ""
        new_tags_raw = self.prompt("Ubah Tag", default=old_tags)
        new_tags = [t.strip() for t in new_tags_raw.split(",") if t.strip()] if new_tags_raw else []

        updated_server = Server(
            alias=new_alias, host=new_host, user=new_user, port=new_port,
            auth_type=new_auth_type, password=new_password, key_path=new_key_path, description=new_desc, tags=new_tags
        )

        val_err = updated_server.validate()
        if val_err:
            print(f"{CLR_RED}\n[!] Gagal menyimpan data: {val_err}{CLR_RESET}")
        else:
            self.servers[selected_idx] = updated_server
            self.save_servers()
            print(f"\n{CLR_GREEN}{ICON_SUCCESS} Data server '{new_alias}' sukses diperbarui!{CLR_RESET}")

        self.prompt("Tekan [Enter] untuk kembali")

    async def menu_remove_server(self):
        if not await self.list_servers_table(check_status=False):
            self.prompt("Tekan [Enter] untuk kembali")
            return

        alias = self.prompt("Ketikkan nama Alias server yang akan dihapus")
        if not alias: return

        target = next((s for s in self.servers if s.alias.lower() == alias.lower()), None)
        if not target:
            print(f"{CLR_RED}[!] Node server tidak dapat dideteksi.{CLR_RESET}")
            self.prompt("Tekan [Enter] untuk kembali")
            return

        confirm = self.prompt(f"Apakah Anda yakin menghapus [{target.alias}] secara permanen? (y/N)", default="n").lower()
        if confirm == 'y':
            self.servers = [s for s in self.servers if s.alias.lower() != target.alias.lower()]
            self.save_servers()
            print(f"{CLR_GREEN}{ICON_SUCCESS} Penghapusan data berhasil.{CLR_RESET}")
        
        self.prompt("Tekan [Enter] untuk kembali")

    async def menu_connect_ssh(self):
        if not await self.list_servers_table(check_status=False):
            self.prompt("Tekan [Enter] untuk kembali")
            return

        target_input = self.prompt("ID / Alias Server sasaran koneksi")
        if not target_input: return

        selected: Optional[Server] = None
        if target_input.isdigit():
            idx = int(target_input) - 1
            if 0 <= idx < len(self.servers):
                selected = self.servers[idx]
        else:
            selected = next((s for s in self.servers if s.alias.lower() == target_input.lower()), None)

        if not selected:
            print(f"{CLR_RED}[!] Target server tidak terdaftar.{CLR_RESET}")
            self.prompt("Tekan [Enter] untuk kembali")
            return

        if selected.auth_type == "password" and not SSHService.is_sshpass_installed():
            print(f"\n{CLR_YELLOW}{ICON_WARN} Peringatan: Aplikasi 'sshpass' tidak terdeteksi.")
            print("Koneksi dialihkan dengan meminta sandi manual pada OpenSSH shell.\n")
            self.prompt("Tekan [Enter] untuk melanjutkan pembuatan sesi")
            selected = Server(
                alias=selected.alias, host=selected.host, user=selected.user,
                port=selected.port, auth_type="password", password=None, description=selected.description
            )

        try:
            cmd = SSHService.build_ssh_command(selected, interactive=True)
            self.clear()
            self.draw_box(
                "KONEKSI SSH AKTIF",
                [
                    f"Host Target : {selected.user}@{selected.host}:{selected.port}",
                    f"Nama Alias  : {selected.alias}",
                    "Ketik 'exit' atau tekan Ctrl+D untuk menutup jalur komunikasi SSH"
                ],
                CLR_GREEN
            )
            subprocess.run(cmd)
        except Exception as e:
            print(f"{CLR_RED}[!] Kendala pada SSH Engine: {e}{CLR_RESET}")

        print(f"\n{CLR_YELLOW}[*] Sesi SSH '{selected.alias}' berhasil diputus.{CLR_RESET}")
        self.prompt("Tekan [Enter] untuk kembali ke Menu Utama")

    async def menu_execute_command(self):
        if not self.servers:
            print(f"{CLR_YELLOW}[!] Database VPS Anda masih kosong.{CLR_RESET}")
            self.prompt("Tekan [Enter] untuk kembali")
            return

        self.clear()
        self.draw_box(
            "MULTIPLE ASYNC COMMAND ENGINE",
            [
                "Mengeksekusi perintah shell secara paralel pada beberapa host",
                "secara asinkron tanpa terjadinya pemblokiran (non-blocking)."
            ],
            CLR_PURPLE
        )
        print("  1) Jalankan perintah pada SATU server pilihan")
        print("  2) Kirimkan perintah massal ke SEMUA server terdaftar")
        choice = self.prompt("Pilih metode pengiriman", default="1")

        targets: List[Server] = []
        if choice == "1":
            await self.list_servers_table(check_status=False)
            target = self.prompt("Masukkan ID/Alias Server")
            if target.isdigit():
                idx = int(target) - 1
                if 0 <= idx < len(self.servers):
                    targets.append(self.servers[idx])
            else:
                s = next((srv for srv in self.servers if srv.alias.lower() == target.lower()), None)
                if s: targets.append(s)
        elif choice == "2":
            targets = self.servers

        if not targets:
            print(f"{CLR_RED}[!] Target server tidak sah!{CLR_RESET}")
            self.prompt("Tekan [Enter] untuk kembali")
            return

        print(f"\n{CLR_BOLD}Daftar Pintasan Perintah (Snippets):{CLR_RESET}")
        for i, sn in enumerate(self.snippets, 1):
            print(f"  [{i}] {CLR_GREEN}{sn.name}{CLR_RESET}: {CLR_GRAY}{sn.command[:45]}...{CLR_RESET}")
        
        cmd_choice = self.prompt("Ketik perintah Bash Anda, atau ketik angka ID Pintasan (Snippet) di atas")
        
        if cmd_choice.isdigit():
            s_idx = int(cmd_choice) - 1
            if 0 <= s_idx < len(self.snippets):
                cmd = self.snippets[s_idx].command
                print(f"[*] Menggunakan Pintasan: {CLR_CYAN}{self.snippets[s_idx].name}{CLR_RESET}")
            else:
                print(f"{CLR_RED}[!] ID Pintasan tidak valid.{CLR_RESET}")
                self.prompt("Tekan [Enter] untuk kembali")
                return
        else:
            cmd = cmd_choice

        if not cmd: return

        print(f"\n{CLR_YELLOW}[*] Menyalurkan perintah ke {len(targets)} server...{CLR_RESET}\n")

        tasks = [SSHService.execute_command_async(srv, cmd) for srv in targets]
        wrapped_task = asyncio.ensure_future(asyncio.gather(*tasks))
        results = await self.run_visual_spinner("Memproses transmisi data asinkron...", wrapped_task)

        for alias, code, stdout, stderr in results:
            print(f"{CLR_BOLD}{CLR_CYAN}[ VPS : {alias} ]{CLR_RESET}")
            if code == 0:
                print(f"{CLR_GREEN}{ICON_SUCCESS} SELESAI (Exit Code: {code}){CLR_RESET}")
                if stdout.strip():
                    print(stdout.strip())
                else:
                    print(f"{CLR_GRAY}(Perintah selesai dijalankan tanpa luapan standar output){CLR_RESET}")
            else:
                print(f"{CLR_RED}[!] GAGAL (Exit Code: {code}){CLR_RESET}")
                if stderr.strip():
                    print(f"{CLR_RED}{stderr.strip()}{CLR_RESET}")
                if stdout.strip():
                    print(f"Stdout Parsial:\n{stdout.strip()}")
            print(f"{CLR_BLUE}{'-' * 70}{CLR_RESET}\n")

        self.prompt("Proses eksekusi selesai. Tekan [Enter] untuk kembali")

    def menu_snippets(self):
        """Fitur Tambahan: Pustaka Pintasan Perintah (Snippets Manager)"""
        while True:
            self.clear()
            self.draw_box(
                "PENGELOLA PINTASAN PERINTAH",
                ["Simpan perintah Bash favorit Anda untuk memudahkan eksekusi massal."],
                CLR_CYAN
            )
            
            if not self.snippets:
                print(f" {CLR_YELLOW}Database Pintasan Kosong.{CLR_RESET}")
            else:
                for idx, sn in enumerate(self.snippets, 1):
                    print(f"  {CLR_CYAN}{idx}.{CLR_RESET} {CLR_BOLD}{sn.name}{CLR_RESET}")
                    print(f"     {CLR_GRAY}Command: {sn.command}{CLR_RESET}")
                    if sn.description:
                        print(f"     Info   : {sn.description}")
                    print()

            print(f"{CLR_CYAN}  [A] Tambah Pintasan Baru  [D] Hapus Pintasan  [X] Kembali ke Menu Utama{RESET}")
            choice = self.prompt("Pilihan").upper()

            if choice == "A":
                name = self.prompt("Nama Pintasan (contoh: Restart-Nginx)")
                if not name: continue
                command = self.prompt("Ketik Perintah Bash")
                if not command: continue
                desc = self.prompt("Penjelasan singkat")
                
                self.snippets.append(Snippet(name=name, command=command, description=desc))
                self.save_snippets()
                print(f"{CLR_GREEN}[✓] Pintasan berhasil disimpan!{CLR_RESET}")
                self.prompt("Tekan [Enter]")
            elif choice == "D":
                target = self.prompt("Masukkan nomor indeks Pintasan yang akan dihapus")
                if target.isdigit():
                    idx = int(target) - 1
                    if 0 <= idx < len(self.snippets):
                        self.snippets.pop(idx)
                        self.save_snippets()
                        print(f"{CLR_GREEN}[✓] Pintasan berhasil dihapus!{CLR_RESET}")
                    else:
                        print(f"{CLR_RED}[!] Indeks di luar jangkauan.{CLR_RESET}")
                self.prompt("Tekan [Enter]")
            elif choice == "X" or not choice:
                break

    def menu_ssh_keygen(self):
        """Fitur Tambahan: Utilitas Generator & Penyalin SSH Key"""
        self.clear()
        self.draw_box(
            "SSH KEY GENERATOR & DEPLOYER",
            [
                "Membuat pasangan kunci SSH baru (RSA/ED25519)",
                "dan menanamkannya ke server tujuan untuk login tanpa password."
            ],
            CLR_PURPLE
        )
        print("  1) Buat Pasangan SSH Key Baru (Lokal)")
        print("  2) Salin/Tanamkan SSH Key ke Server Tujuan (Simulasi ssh-copy-id)")
        opt = self.prompt("Pilih Opsi", default="1")

        if opt == "1":
            key_type = self.prompt("Jenis Kunci (rsa / ed25519)", default="ed25519")
            path = self.prompt("Lokasi penyimpanan file kunci", default="~/.ssh/id_rsa")
            expanded_path = os.path.expanduser(path)
            
            os.makedirs(os.path.dirname(expanded_path), exist_ok=True)
            
            cmd = ["ssh-keygen", "-t", key_type, "-f", expanded_path, "-N", ""]
            try:
                subprocess.run(cmd, check=True)
                print(f"\n{CLR_GREEN}{ICON_SUCCESS} Kunci SSH berhasil dibuat di: {path}{CLR_RESET}")
            except subprocess.CalledProcessError as e:
                print(f"{CLR_RED}[!] Gagal membuat kunci: {e}{CLR_RESET}")
                
        elif opt == "2":
            if not self.servers:
                print(f"{CLR_YELLOW}[!] Daftarkan server terlebih dahulu.{CLR_RESET}")
                self.prompt("Tekan [Enter]")
                return

            self.list_servers_table(check_status=False)
            target_idx = self.prompt("Pilih ID Server Target")
            
            selected: Optional[Server] = None
            if target_idx.isdigit():
                idx = int(target_idx) - 1
                if 0 <= idx < len(self.servers):
                    selected = self.servers[idx]
            
            if not selected:
                print(f"{CLR_RED}[!] Server tidak ditemukan.{CLR_RESET}")
                self.prompt("Tekan [Enter]")
                return

            pub_key_path = self.prompt("Path File Public Key (.pub)", default="~/.ssh/id_rsa.pub")
            expanded_pub = os.path.expanduser(pub_key_path)

            if not os.path.exists(expanded_pub):
                print(f"{CLR_RED}[!] Berkas public key tidak ditemukan di {pub_key_path}{CLR_RESET}")
                self.prompt("Tekan [Enter]")
                return

            with open(expanded_pub, "r") as key_file:
                pub_key_content = key_file.read().strip()

            deploy_cmd = f'mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo "{pub_key_content}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
            
            print(f"\n[*] Mengirimkan public key ke [{selected.alias}]...")
            async def run_deploy():
                return await SSHService.execute_command_async(selected, deploy_cmd)
                
            loop = asyncio.get_event_loop()
            task = loop.create_task(run_deploy())
            alias, code, stdout, stderr = loop.run_until_complete(self.run_visual_spinner("Mentransfer kredensial...", task))

            if code == 0:
                print(f"{CLR_GREEN}{ICON_SUCCESS} SSH Key berhasil ditanamkan! Sekarang Anda dapat mengakses VPS ini tanpa password.{CLR_RESET}")
            else:
                print(f"{CLR_RED}[!] Gagal menanamkan SSH Key: {stderr}{CLR_RESET}")

        self.prompt("\nTekan [Enter] untuk kembali")

    async def run(self):
        while True:
            try:
                self.clear()
                self.draw_box(
                    "VPS & SSH MULTI-MANAGEMENT CONSOLE",
                    [
                        "Asynchronous High-Performance Engine - Enterprise CLI Standard",
                        f"Database: {len(self.servers)} Server Terdaftar | {len(self.snippets)} Pintasan Perintah"
                    ],
                    CLR_PURPLE
                )

                print(f"  {CLR_BOLD}{CLR_CYAN}1.{CLR_RESET} Tampilkan Daftar VPS & Group Tag")
                print(f"  {CLR_BOLD}{CLR_CYAN}2.{CLR_RESET} Monitor Telemetri Vitalitas Server Jarak Jauh (Real-Time)")
                print(f"  {CLR_BOLD}{CLR_CYAN}3.{CLR_RESET} Tambah Server Baru")
                print(f"  {CLR_BOLD}{CLR_CYAN}4.{CLR_RESET} Modifikasi Data Server")
                print(f"  {CLR_BOLD}{CLR_CYAN}5.{CLR_RESET} Hapus Server")
                print(f"  {CLR_BOLD}{CLR_CYAN}6.{CLR_RESET} Sambungkan ke SSH (Auto-Login Sesi Interaktif)")
                print(f"  {CLR_BOLD}{CLR_CYAN}7.{CLR_RESET} Eksekusi Perintah Jarak Jauh / Massal (Async Engine)")
                print(f"  {CLR_BOLD}{CLR_CYAN}8.{CLR_RESET} Pengelola Kunci SSH (Key Gen & Deployer)")
                print(f"  {CLR_BOLD}{CLR_CYAN}9.{CLR_RESET} Pengelola Pintasan Perintah (Snippets Manager)")
                print(f"  {CLR_BOLD}{CLR_RED}0.{CLR_RESET} Tutup Aplikasi")
                print(f"{CLR_PURPLE}{B_H * self.get_layout_width()}{CLR_RESET}\n")

                choice = self.prompt("Pilih Menu Layanan", default="1")

                if choice == "1":
                    tag_f = self.prompt("Saring berdasarkan Tag Kategori (Kosongkan jika ingin menampilkan semua)")
                    await self.list_servers_table(check_status=False, tag_filter=tag_f)
                    self.prompt("Tekan [Enter] untuk kembali ke Menu Utama")
                elif choice == "2":
                    tag_f = self.prompt("Saring berdasarkan Tag Kategori sebelum melakukan pemantauan (Kosongkan untuk memantau semua)")
                    await self.list_servers_table(check_status=True, tag_filter=tag_f)
                    self.prompt("Tekan [Enter] untuk kembali ke Menu Utama")
                elif choice == "3":
                    self.menu_add_server()
                elif choice == "4":
                    await self.menu_edit_server()
                elif choice == "5":
                    await self.menu_remove_server()
                elif choice == "6":
                    await self.menu_connect_ssh()
                elif choice == "7":
                    await self.menu_execute_command()
                elif choice == "8":
                    self.menu_ssh_keygen()
                elif choice == "9":
                    self.menu_snippets()
                elif choice == "0":
                    print(f"\n{CLR_GREEN}✔ Selesai! Terima kasih telah menggunakan VPS Manager CLI.{CLR_RESET}")
                    break
            except KeyboardInterrupt:
                print(f"\n\n{CLR_YELLOW}[*] Sesi terminal ditutup secara aman.{CLR_RESET}")
                sys.exit(0)
