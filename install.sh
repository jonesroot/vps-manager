#!/usr/bin/env bash
# install.sh

set -euo pipefail

RED='\033[91m'
GREEN='\033[92m'
BLUE='\033[94m'
RESET='\033[0m'

echo -e "${BLUE}=== VPS MANAGER INSTALLER FOR ARCH LINUX ===${RESET}"

if [ ! -f /etc/arch-release ]; then
    echo -e "${RED}[!] Peringatan: Script ini didesain khusus untuk Arch Linux.${RESET}"
fi

echo -e "\n[*] Memeriksa paket pendukung..."
if ! command -v sshpass &> /dev/null; then
    echo -e "[*] 'sshpass' tidak ditemukan. Memasang via pacman..."
    sudo pacman -S --needed --noconfirm sshpass
else
    echo -e "${GREEN}[✓] 'sshpass' sudah terpasang.${RESET}"
fi

INSTALL_DIR="/usr/local/share/vps-manager"
echo -e "\n[*] Menyalin source code ke ${INSTALL_DIR}..."

sudo mkdir -p "${INSTALL_DIR}"
sudo cp -r vps_manager "${INSTALL_DIR}/"
sudo cp vpsman "${INSTALL_DIR}/vpsman"

sudo chmod +x "${INSTALL_DIR}/vpsman"

echo -e "[*] Membuat symbolic link di /usr/local/bin..."
sudo ln -sf "${INSTALL_DIR}/vpsman" /usr/local/bin/vpsman

echo -e "\n${GREEN}[✓] INSTALASI BERHASIL!${RESET}"
echo -e "Silakan ketik ${GREEN}vpsman${RESET} di terminal Anda."
