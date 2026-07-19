#!/usr/bin/env bash
# install.sh - Universal Installer for VPS Manager (Enterprise Edition)
# Lucifer 2026

set -euo pipefail

RED='\033[38;2;255;95;95m'
GREEN='\033[38;2;95;255;95m'
YELLOW='\033[38;2;255;215;0m'
BLUE='\033[38;2;95;175;255m'
PURPLE='\033[38;2;175;95;255m'
CYAN='\033[38;2;95;255;255m'
GRAY='\033[38;2;135;135;135m'
RESET='\033[0m'
BOLD='\033[1m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/usr/local/share/vps-manager"
BIN_DIR="/usr/local/bin"

clear
echo -e "${PURPLE}╭───────────────────────────────────────────────────╮${RESET}"
echo -e "${PURPLE}│${RESET}         ${BOLD}${CYAN}VPS MANAGER - ENTERPRISE CLI EDITION${RESET}      ${PURPLE}│${RESET}"
echo -e "${PURPLE}│${RESET}        ${GRAY}Universal Installer & Setup Utility${RESET}        ${PURPLE}│${RESET}"
echo -e "${PURPLE}╰───────────────────────────────────────────────────╯${RESET}\n"

detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID"
    else
        echo "unknown"
    fi
}

OS_TYPE=$(detect_os)
echo -e " ${BOLD}${BLUE}[*]${RESET} Mengidentifikasi Sistem Operasi Host... [${BOLD}${YELLOW}${OS_TYPE}${RESET}]"

install_dependencies() {
    echo -e " ${BOLD}${BLUE}[*]${RESET} Memasang dependensi sistem yang diperlukan..."
    case "$OS_TYPE" in
        "arch"|"manjaro")
            sudo pacman -Sy --needed --noconfirm sshpass openssh python3
            ;;
        "debian"|"ubuntu"|"pop"|"mint")
            sudo apt-get update -y
            sudo apt-get install -y sshpass openssh-client python3
            ;;
        "fedora"|"rhel"|"centos")
            sudo dnf install -y sshpass openssh-clients python3
            ;;
        "alpine")
            sudo apk update
            sudo apk add sshpass openssh-client python3 bash
            ;;
        "macos")
            if ! command -v brew &> /dev/null; then
                echo -e " ${RED}[!] Homebrew tidak terdeteksi. Silakan pasang Homebrew terlebih dahulu.${RESET}"
                exit 1
            fi
            brew install hudochenkov/sshpass/sshpass python3
            ;;
        *)
            echo -e " ${YELLOW}[⚠️] OS tidak didukung secara otomatis. Pastikan 'python3', 'ssh', dan 'sshpass' tersedia.${RESET}"
            ;;
    esac
}

install_dependencies

echo -e "\n ${BOLD}${BLUE}[*]${RESET} Menyiapkan direktori instalasi terisolasi..."
sudo rm -rf "${INSTALL_DIR}"
sudo mkdir -p "${INSTALL_DIR}"

echo -e " ${BOLD}${BLUE}[*]${RESET} Menyalin arsitektur modul sistem..."
sudo cp -r "${SCRIPT_DIR}/vps_manager" "${INSTALL_DIR}/"
sudo cp "${SCRIPT_DIR}/vpsman" "${INSTALL_DIR}/vpsman"

echo -e " ${BOLD}${BLUE}[*]${RESET} Konfigurasi hak akses eksekusi keamanan..."
sudo chmod +x "${INSTALL_DIR}/vpsman"

echo -e " ${BOLD}${BLUE}[*]${RESET} Merelasikan Tautan Simbolis Global ke: ${BOLD}${CYAN}${BIN_DIR}/vpsman${RESET}"
sudo ln -sf "${INSTALL_DIR}/vpsman" "${BIN_DIR}/vpsman"

echo -e "\n${BOLD}${GREEN}╭───────────────────────────────────────────────────╮${RESET}"
echo -e "${BOLD}${GREEN}│        INSTALASI SELESAI DENGAN SUKSES!           │${RESET}"
echo -e "${BOLD}${GREEN}╰───────────────────────────────────────────────────╯${RESET}"
echo -e " Akses aplikasi sekarang dengan perintah global: ${BOLD}${CYAN}vpsman${RESET}\n"
