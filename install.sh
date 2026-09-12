#!/usr/bin/env bash
# ==============================================================================
# VPS Manager Pro :: Enterprise TUI Installer & Lifecycle Orchestrator
# ==============================================================================
# Pure ANSI/VT100 interactive Terminal User Interface installer.
# Supports Debian/Ubuntu, Arch, Fedora/RHEL, Alpine, and macOS.
#
# :copyright: (c) 2025 by Elite Systems Architecture.
# :license: MIT, see LICENSE for more details.
# ==============================================================================

set -euo pipefail
IFS=$'\n\t'

# Color Palette & Styling Directives
readonly COLOR_RESET="\033[0m"
readonly COLOR_BOLD="\033[1m"
readonly COLOR_DIM="\033[2m"
readonly COLOR_CYAN="\033[1;36m"
readonly COLOR_GREEN="\033[1;32m"
readonly COLOR_YELLOW="\033[1;33m"
readonly COLOR_RED="\033[1;31m"
readonly COLOR_BLUE="\033[1;34m"
readonly COLOR_MAGENTA="\033[1;35m"
readonly BG_SELECT="\033[1;44;37m"

# Application Paths
readonly APP_NAME="vps-manager"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Trap cleanup to restore cursor and terminal modes
cleanup() {
    local exit_code=$?
    tput cnorm 2>/dev/null || printf "\033[?25h"
    printf "${COLOR_RESET}\n"
    exit "${exit_code}"
}
trap cleanup SIGINT SIGTERM EXIT

# Hide cursor during TUI rendering
tput civis 2>/dev/null || printf "\033[?25l"

# ==============================================================================
# HELPER UTILITIES
# ==============================================================================

detect_os() {
    if [[ -f /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        echo "${ID:-linux}"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    else
        uname -s | tr '[:upper:]' '[:lower:]'
    fi
}

get_target_home() {
    local target_user="$1"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "/Users/${target_user}"
    else
        getent passwd "${target_user}" | cut -d: -f6 || echo "/home/${target_user}"
    fi
}

log_info() {
    printf "${COLOR_CYAN}ℹ [INFO]${COLOR_RESET} %s\n" "$1"
}

log_success() {
    printf "${COLOR_GREEN}✔ [SUCCESS]${COLOR_RESET} %s\n" "$1"
}

log_warn() {
    printf "${COLOR_YELLOW}⚠ [WARNING]${COLOR_RESET} %s\n" "$1"
}

log_error() {
    printf "${COLOR_RED}✖ [ERROR]${COLOR_RESET} %s\n" "$1"
}

pause_prompt() {
    printf "\n${COLOR_DIM}Press any key to return to main menu...${COLOR_RESET}"
    read -rsn1
}

# ==============================================================================
# TUI MENU COMPONENT
# ==============================================================================

draw_banner() {
    clear
    printf "${COLOR_CYAN}"
    cat << 'EOF'
 ╔══════════════════════════════════════════════════════════════════════════════╗
 ║                       VPS MANAGER PRO :: INSTALLER                           ║
 ║              Enterprise Fleet Orchestration & Telemetry Suite                ║
 ╚══════════════════════════════════════════════════════════════════════════════╝
EOF
    printf "${COLOR_RESET}"
}

render_menu() {
    local -r selected_idx="$1"
    shift
    local -a options=("$@")

    draw_banner
    printf " %b\n\n" "${COLOR_BOLD}Select an action using [↑ / ↓] arrows and press [Enter]:${COLOR_RESET}"

    for i in "${!options[@]}"; do
        if [[ "$i" -eq "$selected_idx" ]]; then
            printf "   ${BG_SELECT}  ➜  %s  ${COLOR_RESET}\n" "${options[$i]}"
        else
            printf "      ${COLOR_DIM}%s${COLOR_RESET}\n" "${options[$i]}"
        fi
    done

    printf "\n ${COLOR_DIM}Navigation: [↑ / k] Up  │  [↓ / j] Down  │  [Enter] Select  │  [q] Quit${COLOR_RESET}\n"
}

# ==============================================================================
# ACTION 1: AUTO SETUP & USER MANAGEMENT
# ==============================================================================

action_auto_setup() {
    clear
    tput cnorm 2>/dev/null || printf "\033[?25h"
    printf "${COLOR_CYAN}${COLOR_BOLD}=== [ AUTO SETUP & USER MANAGEMENT ] ===${COLOR_RESET}\n\n"

    local current_user
    current_user="${SUDO_USER:-$USER}"

    log_info "Detecting system identity..."
    printf "Current session user: ${COLOR_BOLD}%s${COLOR_RESET}\n\n" "$current_user"

    printf "Choose user configuration target:\n"
    printf "  [1] Install for current user (%s)\n" "$current_user"
    printf "  [2] Create a new dedicated Linux system user for VPS Manager\n"
    printf "Choice [1-2] (default 1): "
    read -r user_choice
    user_choice="${user_choice:-1}"

    local target_user="$current_user"

    if [[ "$user_choice" == "2" ]]; then
        if [[ "$EUID" -ne 0 ]]; then
            log_error "Root or sudo privileges are required to create a new system user."
            log_info "Please run: sudo ./install.sh"
            pause_prompt
            return
        fi

        while true; do
            printf "\nEnter new Linux username: "
            read -r target_user
            if [[ -z "$target_user" ]]; then
                log_warn "Username cannot be empty."
                continue
            fi
            if id "$target_user" &>/dev/null; then
                log_warn "User '${target_user}' already exists. Using existing user."
                break
            fi

            log_info "Creating system user '${target_user}'..."
            useradd -m -s /bin/bash "$target_user"
            log_info "Set password for user '${target_user}':"
            passwd "$target_user"
            log_success "User '${target_user}' created successfully."
            break
        done
    fi

    local target_home
    target_home="$(get_target_home "$target_user")"
    local venv_path="${target_home}/.local/share/vps_manager/venv"
    local config_path="${target_home}/.config/vps_manager"
    local bin_symlink="/usr/local/bin/vps-manager"
    local user_bin_dir="${target_home}/.local/bin"

    # Step 1: Package Manager Dependencies
    log_info "Auditing and installing system dependencies..."
    local os_id
    os_id="$(detect_os)"

    case "$os_id" in
        ubuntu|debian)
            if [[ "$EUID" -eq 0 ]]; then
                apt-get update -qq
                apt-get install -y -qq python3 python3-venv python3-pip openssh-client git
            else
                sudo apt-get update -qq
                sudo apt-get install -y -qq python3 python3-venv python3-pip openssh-client git
            fi
            ;;
        arch|manjaro)
            if [[ "$EUID" -eq 0 ]]; then
                pacman -Sy --noconfirm --needed python python-pip openssh git
            else
                sudo pacman -Sy --noconfirm --needed python python-pip openssh git
            fi
            ;;
        fedora|rhel|centos)
            if [[ "$EUID" -eq 0 ]]; then
                dnf install -y -q python3 python3-pip openssh-clients git
            else
                sudo dnf install -y -q python3 python3-pip openssh-clients git
            fi
            ;;
        alpine)
            if [[ "$EUID" -eq 0 ]]; then
                apk add --no-cache python3 py3-pip openssh-client git
            else
                sudo apk add --no-cache python3 py3-pip openssh-client git
            fi
            ;;
        macos)
            if command -v brew &>/dev/null; then
                brew install python openssh git 2>/dev/null || true
            fi
            ;;
        *)
            log_warn "Unrecognized OS distribution: ${os_id}. Assuming python3 >= 3.11 and venv are present."
            ;;
    esac

    # Step 2: Python Version Check (>= 3.11 required)
    log_info "Verifying Python runtime version..."
    if ! command -v python3 &>/dev/null; then
        log_error "Python 3 is not installed or not in PATH."
        pause_prompt
        return
    fi

    local py_ver
    py_ver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    local py_major py_minor
    py_major="$(echo "$py_ver" | cut -d. -f1)"
    py_minor="$(echo "$py_ver" | cut -d. -f2)"

    if [[ "$py_major" -lt 3 ]] || [[ "$py_major" -eq 3 && "$py_minor" -lt 11 ]]; then
        log_error "VPS Manager requires Python >= 3.11. Found: Python ${py_ver}"
        pause_prompt
        return
    fi
    log_success "Python runtime verified: Python ${py_ver}"

    # Step 3: Virtual Environment Setup
    log_info "Creating virtual environment at: ${venv_path}"
    mkdir -p "$(dirname "$venv_path")"
    mkdir -p "$config_path"
    mkdir -p "$user_bin_dir"

    python3 -m venv "$venv_path"

    # Step 4: Package Installation
    log_info "Installing VPS Manager dependencies into venv..."
    "${venv_path}/bin/pip" install --quiet --upgrade pip setuptools wheel
    "${venv_path}/bin/pip" install --quiet -e "$SCRIPT_DIR"

    # Step 5: Binary Launcher Symlink
    local venv_binary="${venv_path}/bin/vps-manager"

    if [[ "$EUID" -eq 0 ]] || sudo -n true 2>/dev/null; then
        log_info "Installing global executable symlink to: ${bin_symlink}"
        if [[ "$EUID" -eq 0 ]]; then
            ln -sf "$venv_binary" "$bin_symlink"
            chmod 755 "$bin_symlink"
        else
            sudo ln -sf "$venv_binary" "$bin_symlink"
            sudo chmod 755 "$bin_symlink"
        fi
    else
        log_info "Installing user executable symlink to: ${user_bin_dir}/vps-manager"
        ln -sf "$venv_binary" "${user_bin_dir}/vps-manager"
        chmod 755 "${user_bin_dir}/vps-manager"
        log_info "Ensure ${user_bin_dir} is in your PATH."
    fi

    # Step 6: Security Hardening (0700 config directory)
    log_info "Hardening permissions on config directory..."
    chmod 700 "$config_path"
    if [[ -f "${config_path}/.vault.key" ]]; then
        chmod 600 "${config_path}/.vault.key"
    fi

    if [[ "$user_choice" == "2" && "$EUID" -eq 0 ]]; then
        chown -R "${target_user}:${target_user}" "$(dirname "$venv_path")"
        chown -R "${target_user}:${target_user}" "$config_path"
    fi

    printf "\n"
    log_success "VPS Manager Pro has been installed successfully!"
    printf "To launch the application, run: ${COLOR_GREEN}${COLOR_BOLD}vps-manager${COLOR_RESET}\n"
    pause_prompt
}

# ==============================================================================
# ACTION 2: UPDATE / REINSTALL DEPENDENCIES
# ==============================================================================

action_update() {
    clear
    tput cnorm 2>/dev/null || printf "\033[?25h"
    printf "${COLOR_CYAN}${COLOR_BOLD}=== [ UPDATE & REINSTALL DEPENDENCIES ] ===${COLOR_RESET}\n\n"

    local current_user="${SUDO_USER:-$USER}"
    local target_home
    target_home="$(get_target_home "$current_user")"
    local venv_path="${target_home}/.local/share/vps_manager/venv"

    if [[ ! -d "$venv_path" ]]; then
        log_error "No existing installation found at: ${venv_path}"
        log_info "Please run 'Auto Setup & Install' first."
        pause_prompt
        return
    fi

    log_info "Updating pip packages inside virtualenv..."
    "${venv_path}/bin/pip" install --upgrade --quiet pip setuptools wheel
    log_info "Re-installing vps-manager package..."
    "${venv_path}/bin/pip" install --upgrade --quiet -e "$SCRIPT_DIR"

    log_success "VPS Manager Pro updated to latest version successfully!"
    pause_prompt
}

# ==============================================================================
# ACTION 3: UNINSTALL (KEEP DATA)
# ==============================================================================

action_uninstall_keep_data() {
    clear
    tput cnorm 2>/dev/null || printf "\033[?25h"
    printf "${COLOR_YELLOW}${COLOR_BOLD}=== [ UNINSTALL (KEEP CONFIGURATION DATA) ] ===${COLOR_RESET}\n\n"

    local current_user="${SUDO_USER:-$USER}"
    local target_home
    target_home="$(get_target_home "$current_user")"
    local venv_path="${target_home}/.local/share/vps_manager"
    local bin_symlink="/usr/local/bin/vps-manager"
    local user_symlink="${target_home}/.local/bin/vps-manager"

    printf "This will remove the Python venv and executables.\n"
    printf "Your server configurations and secret vault keys ${COLOR_GREEN}WILL BE PRESERVED${COLOR_RESET}.\n\n"
    printf "Proceed with uninstall? [y/N]: "
    read -r confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        log_info "Uninstall aborted."
        pause_prompt
        return
    fi

    log_info "Removing virtual environment: ${venv_path}..."
    rm -rf "$venv_path"

    log_info "Removing symlinks..."
    rm -f "$user_symlink"
    if [[ -L "$bin_symlink" ]]; then
        if [[ "$EUID" -eq 0 ]]; then
            rm -f "$bin_symlink"
        elif sudo -n true 2>/dev/null; then
            sudo rm -f "$bin_symlink"
        fi
    fi

    log_success "VPS Manager uninstalled successfully. Configuration preserved at: ${target_home}/.config/vps_manager"
    pause_prompt
}

# ==============================================================================
# ACTION 4: PURGE (UNINSTALL + PURGE ALL DATA)
# ==============================================================================

action_purge_all_data() {
    clear
    tput cnorm 2>/dev/null || printf "\033[?25h"
    printf "${COLOR_RED}${COLOR_BOLD}=== [ PURGE: UNINSTALL & DESTROY ALL DATA ] ===${COLOR_RESET}\n\n"

    local current_user="${SUDO_USER:-$USER}"
    local target_home
    target_home="$(get_target_home "$current_user")"
    local venv_path="${target_home}/.local/share/vps_manager"
    local config_path="${target_home}/.config/vps_manager"
    local bin_symlink="/usr/local/bin/vps-manager"
    local user_symlink="${target_home}/.local/bin/vps-manager"

    printf "${COLOR_RED}${COLOR_BOLD}DANGER: THIS ACTION IS PERMANENT AND IRREVERSIBLE!${COLOR_RESET}\n"
    printf "This will delete:\n"
    printf "  - Virtual environment: %s\n" "$venv_path"
    printf "  - Executable symlinks: %s\n" "$bin_symlink"
    printf "  - ${COLOR_RED}ALL SERVER DATA & ENCRYPTION KEYS: %s${COLOR_RESET}\n\n" "$config_path"
    printf "To confirm, please type '${COLOR_BOLD}PURGE${COLOR_RESET}' in capital letters: "
    read -r confirm

    if [[ "$confirm" != "PURGE" ]]; then
        log_info "Purge cancelled. No changes were made."
        pause_prompt
        return
    fi

    log_info "Purging virtual environment..."
    rm -rf "$venv_path"

    log_info "Purging executable symlinks..."
    rm -f "$user_symlink"
    if [[ -L "$bin_symlink" ]]; then
        if [[ "$EUID" -eq 0 ]]; then
            rm -f "$bin_symlink"
        elif sudo -n true 2>/dev/null; then
            sudo rm -f "$bin_symlink"
        fi
    fi

    log_info "Purging configuration and secret vault keys..."
    rm -rf "$config_path"

    log_success "VPS Manager and all associated data have been completely purged."
    pause_prompt
}

# ==============================================================================
# ACTION 5: BACKUP DATABASE
# ==============================================================================

action_backup() {
    clear
    tput cnorm 2>/dev/null || printf "\033[?25h"
    printf "${COLOR_CYAN}${COLOR_BOLD}=== [ BACKUP SERVER DATABASE ] ===${COLOR_RESET}\n\n"

    local current_user="${SUDO_USER:-$USER}"
    local target_home
    target_home="$(get_target_home "$current_user")"
    local db_file="${target_home}/.config/vps_manager/servers.json"

    if [[ ! -f "$db_file" ]]; then
        log_error "No database file found at: ${db_file}"
        pause_prompt
        return
    fi

    local timestamp
    timestamp="$(date +%Y%m%d_%H%M%S)"
    local backup_target="${SCRIPT_DIR}/vps_backup_${timestamp}.json"

    log_info "Backing up database to: ${backup_target}..."
    cp "$db_file" "$backup_target"
    chmod 600 "$backup_target"

    log_success "Backup created successfully: ${backup_target}"
    pause_prompt
}

# ==============================================================================
# ACTION 6: RESTORE DATABASE
# ==============================================================================

action_restore() {
    clear
    tput cnorm 2>/dev/null || printf "\033[?25h"
    printf "${COLOR_CYAN}${COLOR_BOLD}=== [ RESTORE SERVER DATABASE ] ===${COLOR_RESET}\n\n"

    local current_user="${SUDO_USER:-$USER}"
    local target_home
    target_home="$(get_target_home "$current_user")"
    local db_file="${target_home}/.config/vps_manager/servers.json"

    printf "Enter path to backup JSON file: "
    read -e -r backup_source

    if [[ ! -f "$backup_source" ]]; then
        log_error "Backup file does not exist: ${backup_source}"
        pause_prompt
        return
    fi

    mkdir -p "$(dirname "$db_file")"
    chmod 700 "$(dirname "$db_file")"
    cp "$backup_source" "$db_file"
    chmod 600 "$db_file"

    log_success "Database restored successfully to: ${db_file}"
    pause_prompt
}

# ==============================================================================
# ACTION 7: DIAGNOSTIC & SECURITY AUDIT
# ==============================================================================

action_diagnostic() {
    clear
    tput cnorm 2>/dev/null || printf "\033[?25h"
    printf "${COLOR_CYAN}${COLOR_BOLD}=== [ SYSTEM DIAGNOSTIC & SECURITY AUDIT ] ===${COLOR_RESET}\n\n"

    local current_user="${SUDO_USER:-$USER}"
    local target_home
    target_home="$(get_target_home "$current_user")"
    local config_dir="${target_home}/.config/vps_manager"
    local vault_key="${config_dir}/.vault.key"
    local db_file="${config_dir}/servers.json"
    local venv_bin="${target_home}/.local/share/vps_manager/venv/bin/vps-manager"

    printf "Checking system components:\n"

    # 1. Python check
    if command -v python3 &>/dev/null; then
        local pver
        pver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
        log_success "Python runtime: ${pver}"
    else
        log_error "Python 3 is missing."
    fi

    # 2. OpenSSH check
    if command -v ssh &>/dev/null; then
        local ssh_ver
        ssh_ver="$(ssh -V 2>&1 | head -n1)"
        log_success "OpenSSH client: ${ssh_ver}"
    else
        log_error "OpenSSH client is missing."
    fi

    # 3. Virtual Environment check
    if [[ -x "$venv_bin" ]]; then
        log_success "Venv executable: ${venv_bin} [Active]"
    else
        log_warn "Venv executable: Not found or not executable."
    fi

    # 4. Config permissions check
    if [[ -d "$config_dir" ]]; then
        local perm
        perm="$(stat -c "%a" "$config_dir" 2>/dev/null || stat -f "%Lp" "$config_dir" 2>/dev/null || echo "unknown")"
        if [[ "$perm" == "700" ]]; then
            log_success "Config directory permissions: 0700 [Secure]"
        else
            log_warn "Config directory permissions: 0${perm} (Expected: 0700)"
        fi
    else
        log_info "Config directory has not been initialized yet."
    fi

    # 5. Vault key check
    if [[ -f "$vault_key" ]]; then
        local kperm
        kperm="$(stat -c "%a" "$vault_key" 2>/dev/null || stat -f "%Lp" "$vault_key" 2>/dev/null || echo "unknown")"
        if [[ "$kperm" == "600" ]]; then
            log_success "Master secret vault key: 0600 [Encrypted at rest]"
        else
            log_warn "Master secret vault key permissions: 0${kperm} (Expected: 0600)"
        fi
    fi

    # 6. Database count check
    if [[ -f "$db_file" ]]; then
        local server_count
        server_count="$(grep -o '"id":' "$db_file" | wc -l || echo "0")"
        log_success "Registered server nodes: ${server_count} nodes"
    fi

    pause_prompt
}

# ==============================================================================
# MAIN TUI EVENT LOOP
# ==============================================================================

main() {
    local -a menu_items=(
        "1) Auto Setup & User Manager (Install dependencies, configure user & venv)"
        "2) Update & Reinstall (Upgrade dependencies inside active venv)"
        "3) Backup Fleet Database (Export current servers.json to archive)"
        "4) Restore Fleet Database (Import database from backup archive)"
        "5) Diagnostic & Security Audit (Verify permissions, Python, SSH)"
        "6) Uninstall (Remove venv and binaries, KEEP server data)"
        "7) Purge All Data (DANGER: Completely wipe venv, keys & server data)"
        "8) Exit Installer"
    )

    local current_selection=0
    local num_options="${#menu_items[@]}"

    while true; do
        render_menu "$current_selection" "${menu_items[@]}"

        # Read single keypress (escape sequence parsing for arrow keys)
        local key
        IFS= read -rsn1 key
        if [[ "$key" == $'\x1b' ]]; then
            read -rsn2 key
            case "$key" in
                '[A') # Arrow Up
                    ((current_selection--)) || true
                    if [[ "$current_selection" -lt 0 ]]; then
                        current_selection=$((num_options - 1))
                    fi
                    ;;
                '[B') # Arrow Down
                    ((current_selection++)) || true
                    if [[ "$current_selection" -ge "$num_options" ]]; then
                        current_selection=0
                    fi
                    ;;
            esac
        elif [[ "$key" == "k" || "$key" == "K" ]]; then
            ((current_selection--)) || true
            if [[ "$current_selection" -lt 0 ]]; then
                current_selection=$((num_options - 1))
            fi
        elif [[ "$key" == "j" || "$key" == "J" ]]; then
            ((current_selection++)) || true
            if [[ "$current_selection" -ge "$num_options" ]]; then
                current_selection=0
            fi
        elif [[ "$key" == "" ]]; then # Enter pressed
            case "$current_selection" in
                0) action_auto_setup ;;
                1) action_update ;;
                2) action_backup ;;
                3) action_restore ;;
                4) action_diagnostic ;;
                5) action_uninstall_keep_data ;;
                6) action_purge_all_data ;;
                7) clear; exit 0 ;;
            esac
        elif [[ "$key" == "q" || "$key" == "Q" ]]; then
            clear
            exit 0
        elif [[ "$key" =~ ^[1-8]$ ]]; then
            local direct_idx=$((key - 1))
            case "$direct_idx" in
                0) action_auto_setup ;;
                1) action_update ;;
                2) action_backup ;;
                3) action_restore ;;
                4) action_diagnostic ;;
                5) action_uninstall_keep_data ;;
                6) action_purge_all_data ;;
                7) clear; exit 0 ;;
            esac
        fi
    done
}

main "$@"
