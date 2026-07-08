# SSH/VPS Manager (`vpsman`)

Pengelola koneksi SSH VPS interaktif, berkinerja tinggi, dan aman berbasis terminal, dibuat khusus untuk pengguna **Arch Linux**.

## Fitur Utama

- **Penyimpanan Sangat Aman**: Konfigurasi VPS dikunci dengan permission `600` di `~/.config/vps-manager/servers.json`.
- **Dukungan Autentikasi Ganda**: Mendukung koneksi menggunakan **Password** (otomatis menggunakan `sshpass`) atau **SSH Keyfile**.
- **Input Password Rahasia**: Menyembunyikan karakter password saat input di terminal (masking).
- **Asynchronous Health Check**: Memeriksa status hidup/mati VPS secara paralel sehingga sangat cepat.
- **Eksekusi Perintah Massal**: Menjalankan instruksi shell secara serentak di satu atau seluruh server Anda.

## Cara Instalasi

Klon repositori ini ke komputer lokal Anda, lalu jalankan script instalasi:

```bash
git clone https://github.com/USER_ANDA/vps-manager.git
cd vps-manager
chmod +x install.sh
./install.sh
```
