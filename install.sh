#!/usr/bin/env bash
# install.sh - Universal Installer for VPS Manager
# Mendukung: Arch, Debian, Ubuntu, Fedora, CentOS, Alpine, dan macOS.
# ⚡ Lucifer VPS Manager — v2.0 ⚡

set -euo pipefail

# ─────────────────────────────────────────────
#  WARNA & GAYA TERMINAL
# ─────────────────────────────────────────────
RED='\033[91m';    GREEN='\033[92m'; YELLOW='\033[93m'
BLUE='\033[94m';   MAGENTA='\033[95m'; CYAN='\033[96m'
WHITE='\033[97m';  DIM='\033[2m';    BOLD='\033[1m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
get_width() { tput cols 2>/dev/null || echo 80; }

print_center() {
    local text="$1" color="${2:-$RESET}"
    local width; width=$(get_width)
    local text_len=${#text}
    local pad=$(( (width - text_len) / 2 ))
    printf "%${pad}s" ""
    echo -e "${color}${text}${RESET}"
}

draw_line() {
    local char="${1:-─}" color="${2:-$BLUE}"
    local width; width=$(get_width)
    local line; line=$(printf '%*s' "$width" | tr ' ' "$char")
    echo -e "${color}${line}${RESET}"
}

spinner() {
    local pid=$1 msg="${2:-Memproses...}"
    local frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    local i=0
    while kill -0 "$pid" 2>/dev/null; do
        printf "\r   ${CYAN}${frames[$i]}${RESET}  ${DIM}${msg}${RESET}   "
        i=$(( (i + 1) % 10 ))
        sleep 0.1
    done
    printf "\r%*s\r" "$(get_width)" ""
}

progress_bar() {
    local current=$1 total=$2 label="${3:-}"
    local width=40
    local filled=$(( current * width / total ))
    local empty=$(( width - filled ))
    local bar; bar="$(printf '%*s' "$filled" | tr ' ' '█')$(printf '%*s' "$empty" | tr ' ' '░')"
    local pct=$(( current * 100 / total ))
    printf "\r  ${CYAN}[${GREEN}%s${CYAN}]${RESET} ${BOLD}%3d%%${RESET}  ${DIM}%s${RESET}  " "$bar" "$pct" "$label"
}

log_ok()   { echo -e "  ${GREEN}✔${RESET}  $*"; }
log_info() { echo -e "  ${CYAN}◈${RESET}  $*"; }
log_warn() { echo -e "  ${YELLOW}▲${RESET}  $*"; }
log_err()  { echo -e "  ${RED}✖${RESET}  $*"; }

# ─────────────────────────────────────────────
#  BANNER
# ─────────────────────────────────────────────
show_banner() {
    clear
    echo ""
    draw_line "═" "$BLUE"
    echo ""
    print_center "██╗   ██╗██████╗ ███████╗    ███╗   ███╗ ██████╗ ██████╗ " "$CYAN"
    print_center "██║   ██║██╔══██╗██╔════╝    ████╗ ████║██╔════╝ ██╔══██╗" "$CYAN"
    print_center "██║   ██║██████╔╝███████╗    ██╔████╔██║██║  ███╗██████╔╝" "$BLUE"
    print_center "╚██╗ ██╔╝██╔═══╝ ╚════██║    ██║╚██╔╝██║██║   ██║██╔══██╗" "$BLUE"
    print_center " ╚████╔╝ ██║     ███████║    ██║ ╚═╝ ██║╚██████╔╝██║  ██║" "$MAGENTA"
    print_center "  ╚═══╝  ╚═╝     ╚══════╝    ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝" "$MAGENTA"
    echo ""
    print_center "Universal SSH Console Manager  ·  Enterprise CLI Edition" "$DIM"
    print_center "⚡  Lucifer  ·  v2.0.0  ·  2025  ⚡" "$YELLOW"
    echo ""
    draw_line "═" "$BLUE"
    echo ""
}

# ─────────────────────────────────────────────
#  DETEKSI OS
# ─────────────────────────────────────────────
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then echo "macos"
    elif [ -f /etc/os-release ]; then
        . /etc/os-release; echo "${ID,,}"
    else echo "unknown"; fi
}

detect_pkg_manager() {
    case "$1" in
        arch|manjaro|endeavouros)              echo "pacman" ;;
        debian|ubuntu|pop|mint|kali|parrot)    echo "apt" ;;
        fedora|rhel|centos|rocky|almalinux)    echo "dnf" ;;
        alpine)                                 echo "apk" ;;
        macos)                                  echo "brew" ;;
        *)                                      echo "unknown" ;;
    esac
}

# ─────────────────────────────────────────────
#  INSTALASI DEPENDENSI
# ─────────────────────────────────────────────
install_dependencies() {
    local os="$1"
    local pkg_mgr; pkg_mgr=$(detect_pkg_manager "$os")
    local deps=("python3" "ssh" "sshpass")

    log_info "Package manager: ${BOLD}${YELLOW}${pkg_mgr}${RESET}"
    echo ""

    case "$pkg_mgr" in
        pacman)
            (sudo pacman -Sy --needed --noconfirm sshpass openssh python &>/dev/null) &
            spinner $! "Mengambil paket dari repositori Arch..."
            wait ;;
        apt)
            (sudo apt-get update -y &>/dev/null) &
            spinner $! "Memperbarui indeks paket APT..."
            wait
            (sudo apt-get install -y sshpass openssh-client python3 &>/dev/null) &
            spinner $! "Memasang dependensi..."
            wait ;;
        dnf)
            (sudo dnf install -y sshpass openssh-clients python3 &>/dev/null) &
            spinner $! "Memasang paket via DNF..."
            wait ;;
        apk)
            (sudo apk update &>/dev/null && sudo apk add sshpass openssh-client python3 bash &>/dev/null) &
            spinner $! "Memasang paket Alpine..."
            wait ;;
        brew)
            if ! command -v brew &>/dev/null; then
                log_err "Homebrew tidak ditemukan. Kunjungi: ${CYAN}https://brew.sh${RESET}"
                exit 1
            fi
            (brew install hudochenkov/sshpass/sshpass python3 &>/dev/null) &
            spinner $! "Mengambil formula Homebrew..."
            wait ;;
        *)
            log_warn "OS tidak dikenali. Pastikan ${BOLD}python3${RESET}, ${BOLD}ssh${RESET}, dan ${BOLD}sshpass${RESET} tersedia." ;;
    esac

    local idx=0
    for dep in "${deps[@]}"; do
        idx=$(( idx + 1 ))
        progress_bar "$idx" "${#deps[@]}" "Verifikasi $dep..."
        sleep 0.25
    done
    echo ""
}

# ─────────────────────────────────────────────
#  VERIFIKASI ENVIRONMENT
# ─────────────────────────────────────────────
verify_environment() {
    local all_ok=true
    local checks=("python3" "ssh")

    echo ""
    log_info "Verifikasi environment runtime..."
    echo ""

    for cmd in "${checks[@]}"; do
        if command -v "$cmd" &>/dev/null; then
            local ver; ver=$("$cmd" --version 2>&1 | head -1)
            log_ok "${BOLD}${cmd}${RESET}  ${DIM}→  ${ver}${RESET}"
        else
            log_err "${BOLD}${cmd}${RESET} tidak ditemukan dalam PATH!"
            all_ok=false
        fi
    done

    if command -v sshpass &>/dev/null; then
        log_ok "${BOLD}sshpass${RESET}  ${DIM}→  tersedia${RESET}"
    else
        log_warn "${BOLD}sshpass${RESET}  ${DIM}→  tidak tersedia (mode password manual aktif)${RESET}"
    fi

    echo ""
    if [ "$all_ok" = false ]; then
        log_err "Dependensi kritis tidak terpenuhi. Hentikan instalasi."
        exit 1
    fi
}

# ─────────────────────────────────────────────
#  DEPLOYMENT FILE APLIKASI
# ─────────────────────────────────────────────
install_app_files() {
    local INSTALL_DIR="/usr/local/share/vps-manager"
    local BIN_DIR="/usr/local/bin"
    local files=("vps_manager/" "vpsman")

    echo ""
    log_info "Mempersiapkan direktori instalasi..."
    (sudo rm -rf "${INSTALL_DIR}" && sudo mkdir -p "${INSTALL_DIR}") &
    spinner $! "Membersihkan instalasi lama..."
    wait
    log_ok "Direktori ${BOLD}${INSTALL_DIR}${RESET} siap"
    echo ""

    local idx=0
    for f in "${files[@]}"; do
        idx=$(( idx + 1 ))
        progress_bar "$idx" "${#files[@]}" "Menyalin ${f}..."
        sleep 0.3
    done
    echo ""

    sudo cp -r "${SCRIPT_DIR}/vps_manager" "${INSTALL_DIR}/"
    sudo cp "${SCRIPT_DIR}/vpsman" "${INSTALL_DIR}/vpsman"
    sudo chmod +x "${INSTALL_DIR}/vpsman"
    log_ok "Berkas aplikasi tersalin ke ${BOLD}${INSTALL_DIR}${RESET}"

    (sudo ln -sf "${INSTALL_DIR}/vpsman" "${BIN_DIR}/vpsman") &
    spinner $! "Membuat symlink global..."
    wait
    log_ok "Symlink aktif di ${BOLD}${BIN_DIR}/vpsman${RESET}"
}

# ─────────────────────────────────────────────
#  RINGKASAN AKHIR
# ─────────────────────────────────────────────
show_summary() {
    local os="$1"
    local width; width=$(get_width)
    local pad=$(( (width - 56) / 2 ))

    echo ""
    draw_line "═" "$GREEN"
    echo ""
    print_center "✔   INSTALASI BERHASIL SEMPURNA   ✔" "${BOLD}${GREEN}"
    echo ""
    draw_line "─" "$DIM"
    echo ""
    printf "%${pad}s" ""; echo -e "  ${DIM}OS Terdeteksi   ${RESET}:  ${YELLOW}${BOLD}${os}${RESET}"
    printf "%${pad}s" ""; echo -e "  ${DIM}Lokasi Install  ${RESET}:  ${CYAN}/usr/local/share/vps-manager${RESET}"
    printf "%${pad}s" ""; echo -e "  ${DIM}Perintah Global ${RESET}:  ${BOLD}${GREEN}vpsman${RESET}"
    printf "%${pad}s" ""; echo -e "  ${DIM}Konfigurasi     ${RESET}:  ${CYAN}~/.config/vps-manager/${RESET}"
    echo ""
    draw_line "─" "$DIM"
    echo ""
    print_center "Jalankan  →  vpsman  ←  dari terminal mana pun untuk memulai" "$CYAN"
    echo ""
    draw_line "═" "$BLUE"
    echo ""
}

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
main() {
    show_banner

    local OS_TYPE; OS_TYPE=$(detect_os)
    log_info "Sistem operasi: ${BOLD}${YELLOW}${OS_TYPE}${RESET}"
    echo ""
    draw_line "─" "$DIM"

    echo ""
    echo -e "  ${BOLD}${CYAN}[ 1 / 3 ]${RESET}  ${BOLD}Instalasi Dependensi${RESET}"
    draw_line "─" "$DIM"
    install_dependencies "$OS_TYPE"
    log_ok "Semua dependensi berhasil dipasang"

    echo ""
    draw_line "─" "$DIM"
    echo -e "  ${BOLD}${CYAN}[ 2 / 3 ]${RESET}  ${BOLD}Verifikasi Environment${RESET}"
    draw_line "─" "$DIM"
    verify_environment

    echo ""
    draw_line "─" "$DIM"
    echo -e "  ${BOLD}${CYAN}[ 3 / 3 ]${RESET}  ${BOLD}Deployment Aplikasi${RESET}"
    draw_line "─" "$DIM"
    install_app_files

    show_summary "$OS_TYPE"
}

main "$@"
