#!/usr/bin/env bash
# ==============================================================================
# VPS MANAGER PRO - AUTOMATED BOOTSTRAP & INSTALLATION ENGINE
# ==============================================================================
set -euo pipefail
IFS=$'\n\t'

# ANSI Color Palette
readonly C_RESET='\033[0m'
readonly C_BOLD='\033[1m'
readonly C_RED='\033[31m'
readonly C_GREEN='\033[32m'
readonly C_YELLOW='\033[33m'
readonly C_BLUE='\033[34m'
readonly C_CYAN='\033[36m'

# Application Configuration
readonly APP_NAME="vps-manager"
readonly APP_DISPLAY="VPS Manager Pro"
readonly MIN_PYTHON_MAJOR=3
readonly MIN_PYTHON_MINOR=11

# Global Path State
TMP_DIR=""
INSTALL_ROOT=""
VENV_DIR=""
BIN_DIR=""
TARGET_BIN=""
PYTHON_SYSTEM_BIN=""
OS_TYPE=""
DISTRO=""

# ==============================================================================
# LOGGING UTILITIES
# ==============================================================================

log_info() {
    printf "${C_BLUE}${C_BOLD}[INFO]${C_RESET} %s\n" "$*"
}

log_step() {
    printf "${C_CYAN}${C_BOLD}[STEP]${C_RESET} %s\n" "$*"
}

log_success() {
    printf "${C_GREEN}${C_BOLD}[SUCCESS]${C_RESET} %s\n" "$*"
}

log_warn() {
    printf "${C_YELLOW}${C_BOLD}[WARN]${C_RESET} %s\n" "$*"
}

log_error() {
    printf "${C_RED}${C_BOLD}[ERROR]${C_RESET} %s\n" "$*" >&2
}

log_fatal() {
    log_error "$*"
    exit 1
}

# ==============================================================================
# DETERMINISTIC TRAP CLEANUP
# ==============================================================================

cleanup() {
    local exit_code=$?
    trap - SIGINT SIGTERM EXIT

    if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
        rm -rf "${TMP_DIR}"
    fi

    if [[ ${exit_code} -ne 0 ]]; then
        printf "\n${C_RED}${C_BOLD}Installation aborted or failed with exit code %s.${C_RESET}\n" "${exit_code}" >&2
    fi
    exit "${exit_code}"
}
trap cleanup SIGINT SIGTERM EXIT

# ==============================================================================
# PRIVILEGE RESOLVER
# ==============================================================================

run_elevated() {
    if [[ "$(id -u)" -eq 0 ]]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    elif command -v doas >/dev/null 2>&1; then
        doas "$@"
    else
        log_fatal "Superuser privileges required for package management, but neither sudo nor doas is available."
    fi
}

# ==============================================================================
# PLATFORM AUDIT & PYTHON DISCOVERY
# ==============================================================================

detect_os_and_distro() {
    OS_TYPE="$(uname -s)"
    DISTRO="unknown"

    case "${OS_TYPE}" in
        Linux)
            if [[ -f /etc/os-release ]]; then
                # shellcheck source=/dev/null
                DISTRO="$(. /etc/os-release && echo "${ID:-unknown}")"
            fi
            ;;
        Darwin)
            DISTRO="macos"
            ;;
        *)
            log_fatal "Unsupported operating system: ${OS_TYPE}."
            ;;
    esac
}

find_suitable_python() {
    local candidate_bins=("python3.13" "python3.12" "python3.11" "python3" "python")
    for bin_name in "${candidate_bins[@]}"; do
        if command -v "${bin_name}" >/dev/null 2>&1; then
            local bin_path
            bin_path="$(command -v "${bin_name}")"
            local is_valid
            is_valid="$("${bin_path}" -c "import sys; print(1 if sys.version_info >= (${MIN_PYTHON_MAJOR}, ${MIN_PYTHON_MINOR}) else 0)" 2>/dev/null || echo 0)"
            if [[ "${is_valid}" -eq 1 ]]; then
                PYTHON_SYSTEM_BIN="${bin_path}"
                return 0
            fi
        fi
    done
    return 1
}

# ==============================================================================
# OS PACKAGE PROVISIONER
# ==============================================================================

install_system_dependencies() {
    log_info "Attempting automated installation of Python >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}..."

    case "${DISTRO}" in
        ubuntu|debian|linuxmint|pop)
            log_step "Updating apt repository cache..."
            run_elevated apt-get update -y
            log_step "Installing Python3, pip, venv, and development tools..."
            run_elevated apt-get install -y --no-install-recommends \
                python3 \
                python3-pip \
                python3-venv \
                python3-dev \
                build-essential \
                curl
            ;;
        fedora)
            log_step "Installing packages via dnf..."
            run_elevated dnf install -y \
                python3 \
                python3-pip \
                python3-devel \
                gcc \
                curl
            ;;
        rhel|centos|rocky|almalinux)
            log_step "Installing packages via dnf..."
            run_elevated dnf install -y epel-release || true
            run_elevated dnf install -y \
                python311 \
                python311-pip \
                python311-devel \
                gcc \
                curl
            ;;
        arch|manjaro)
            log_step "Installing packages via pacman..."
            run_elevated pacman -Syu --noconfirm --needed \
                python \
                python-pip \
                base-devel \
                curl
            ;;
        alpine)
            log_step "Installing packages via apk..."
            run_elevated apk add --no-cache \
                python3 \
                py3-pip \
                python3-dev \
                build-base \
                curl
            ;;
        opensuse*|sles)
            log_step "Installing packages via zypper..."
            run_elevated zypper refresh
            run_elevated zypper install -y \
                python311 \
                python311-pip \
                python311-devel \
                gcc \
                curl
            ;;
        macos)
            if ! command -v brew >/dev/null 2>&1; then
                log_fatal "Homebrew is required on macOS. Please install Homebrew from https://brew.sh first."
            fi
            log_step "Installing Python via Homebrew..."
            brew install python@3.11 curl
            ;;
        *)
            log_fatal "Distribution '${DISTRO}' not supported for automatic package provisioning. Please install Python >= 3.11 manually."
            ;;
    esac
}

# ==============================================================================
# INSTALLATION PATH RESOLVER
# ==============================================================================

configure_install_paths() {
    local is_root=0
    if [[ "$(id -u)" -eq 0 ]]; then
        is_root=1
    fi

    if [[ "${is_root}" -eq 1 ]]; then
        INSTALL_ROOT="/opt/vps_manager"
        BIN_DIR="/usr/local/bin"
    else
        INSTALL_ROOT="${HOME}/.local/share/vps_manager"
        BIN_DIR="${HOME}/.local/bin"
    fi

    VENV_DIR="${INSTALL_ROOT}/venv"
    TARGET_BIN="${BIN_DIR}/${APP_NAME}"

    mkdir -p "${INSTALL_ROOT}" "${BIN_DIR}"
    chmod 0755 "${INSTALL_ROOT}" "${BIN_DIR}"
}

# ==============================================================================
# VIRTUAL ENVIRONMENT & PACKAGE BUILD
# ==============================================================================

provision_virtualenv() {
    log_step "Initializing isolated virtual environment at '${VENV_DIR}'..."

    if [[ ! -f "${VENV_DIR}/bin/python" ]]; then
        "${PYTHON_SYSTEM_BIN}" -m venv "${VENV_DIR}"
    fi

    local venv_pip="${VENV_DIR}/bin/pip"

    log_step "Upgrading core packaging infrastructure (pip, setuptools, wheel)..."
    "${venv_pip}" install --upgrade --no-input --quiet pip setuptools wheel

    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # Defensive Guard: Ensure README.md exists to satisfy Hatchling metadata requirements
    if [[ ! -f "${script_dir}/README.md" ]]; then
        log_info "Creating default README.md to satisfy build metadata..."
        cat <<'EOF' > "${script_dir}/README.md"
# VPS Manager Pro

Modern, cross-platform interactive TUI for VPS fleet orchestration.
EOF
    fi

    log_step "Installing dependencies for ${APP_DISPLAY}..."

    if [[ -f "${script_dir}/pyproject.toml" && -d "${script_dir}/vps_manager" ]]; then
        log_info "Detected local repository at '${script_dir}'. Installing in editable mode..."
        "${venv_pip}" install --no-input -e "${script_dir}"
    else
        log_info "Installing direct distribution package..."
        "${venv_pip}" install --no-input \
            "textual>=0.50.0" \
            "rich>=13.7.0" \
            "asyncssh>=2.14.2" \
            "cryptography>=42.0.0"

        mkdir -p "${INSTALL_ROOT}/lib"
        if [[ -d "${script_dir}/vps_manager" ]]; then
            cp -r "${script_dir}/vps_manager" "${INSTALL_ROOT}/lib/"
            "${venv_pip}" install --no-input "${INSTALL_ROOT}/lib"
        fi
    fi
}

# ==============================================================================
# BINARY LAUNCHER WRAPPER
# ==============================================================================

generate_binary_wrapper() {
    log_step "Deploying binary launcher to '${TARGET_BIN}'..."

    cat <<EOF > "${TARGET_BIN}"
#!/usr/bin/env bash
# Autogenerated launcher wrapper for ${APP_DISPLAY}
set -e
exec "${VENV_DIR}/bin/${APP_NAME}" "\$@"
EOF

    chmod 0755 "${TARGET_BIN}"
}

# ==============================================================================
# SHELL INTEGRATION (FISH / ZSH / BASH AWARE)
# ==============================================================================

ensure_path_integration() {
    if [[ ":${PATH}:" == *":${BIN_DIR}:"* ]]; then
        return 0
    fi

    log_warn "Binary directory '${BIN_DIR}' is not present in active \$PATH."

    local current_shell
    current_shell="$(basename "${SHELL:-/bin/bash}")"

    case "${current_shell}" in
        fish)
            local fish_config_dir="${HOME}/.config/fish"
            local fish_config="${fish_config_dir}/config.fish"
            mkdir -p "${fish_config_dir}"

            if command -v fish >/dev/null 2>&1; then
                fish -c "fish_add_path -m '${BIN_DIR}'" 2>/dev/null || true
            fi

            if ! grep -qs "${BIN_DIR}" "${fish_config}" 2>/dev/null; then
                log_step "Adding path configuration to '${fish_config}'..."
                printf "\n# Added by %s Auto-Setup\nset -gx PATH \"%s\" \$PATH\n" "${APP_DISPLAY}" "${BIN_DIR}" >> "${fish_config}"
            fi
            log_info "Fish configuration updated. Path will be active on next command."
            ;;
        zsh)
            local zsh_rc="${HOME}/.zshrc"
            if ! grep -qs "${BIN_DIR}" "${zsh_rc}" 2>/dev/null; then
                log_step "Adding path export to '${zsh_rc}'..."
                printf "\n# Added by %s Auto-Setup\nexport PATH=\"%s:\$PATH\"\n" "${APP_DISPLAY}" "${BIN_DIR}" >> "${zsh_rc}"
                log_info "Zsh configuration updated. Run: source ${zsh_rc}"
            fi
            ;;
        bash)
            local bash_rc="${HOME}/.bashrc"
            [[ -f "${HOME}/.bash_profile" ]] && bash_rc="${HOME}/.bash_profile"
            if ! grep -qs "${BIN_DIR}" "${bash_rc}" 2>/dev/null; then
                log_step "Adding path export to '${bash_rc}'..."
                printf "\n# Added by %s Auto-Setup\nexport PATH=\"%s:\$PATH\"\n" "${APP_DISPLAY}" "${BIN_DIR}" >> "${bash_rc}"
                log_info "Bash configuration updated. Run: source ${bash_rc}"
            fi
            ;;
        *)
            local profile="${HOME}/.profile"
            if ! grep -qs "${BIN_DIR}" "${profile}" 2>/dev/null; then
                log_step "Adding path export to '${profile}'..."
                printf "\n# Added by %s Auto-Setup\nexport PATH=\"%s:\$PATH\"\n" "${APP_DISPLAY}" "${BIN_DIR}" >> "${profile}"
            fi
            ;;
    esac
}

# ==============================================================================
# SMOKE TEST
# ==============================================================================

verify_installation() {
    log_step "Running diagnostic smoke test..."

    if [[ ! -x "${TARGET_BIN}" ]]; then
        log_fatal "Launcher binary was not generated at '${TARGET_BIN}'."
    fi

    local version_output
    if ! version_output="$("${TARGET_BIN}" --version 2>&1)"; then
        log_fatal "Smoke test failed with runtime error:\n${version_output}"
    fi

    if [[ "${version_output}" != *"vps-manager"* ]]; then
        log_fatal "Smoke test failed. Unexpected output: ${version_output}"
    fi

    log_success "Sanity check passed: ${version_output}"
}

# ==============================================================================
# ENTRYPOINT
# ==============================================================================

main() {
    printf "\n"
    printf "${C_CYAN}${C_BOLD}====================================================================${C_RESET}\n"
    printf "${C_CYAN}${C_BOLD}       %s - Automated Enterprise Setup Engine       ${C_RESET}\n" "${APP_DISPLAY}"
    printf "${C_CYAN}${C_BOLD}====================================================================${C_RESET}\n\n"

    TMP_DIR="$(mktemp -d -t vpsman_install_XXXXXX)"
    chmod 0700 "${TMP_DIR}"

    detect_os_and_distro
    log_info "Environment: ${OS_TYPE} (${DISTRO})"

    if ! find_suitable_python; then
        log_warn "Python >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR} not detected."
        install_system_dependencies
        if ! find_suitable_python; then
            log_fatal "Could not locate Python >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR} after provisioning."
        fi
    fi

    log_success "Target Python: ${PYTHON_SYSTEM_BIN} ($("${PYTHON_SYSTEM_BIN}" --version))"

    configure_install_paths
    provision_virtualenv
    generate_binary_wrapper
    ensure_path_integration
    verify_installation

    printf "\n"
    printf "${C_GREEN}${C_BOLD}====================================================================${C_RESET}\n"
    printf "${C_GREEN}${C_BOLD}                INSTALLATION COMPLETED SUCCESSFULLY!                ${C_RESET}\n"
    printf "${C_GREEN}${C_BOLD}====================================================================${C_RESET}\n"
    printf "${C_BOLD}Executable Target :${C_RESET} %s\n" "${TARGET_BIN}"
    printf "${C_BOLD}Environment Root  :${C_RESET} %s\n\n" "${VENV_DIR}"
    printf "Launch the application by running:\n"
    printf "  ${C_CYAN}${C_BOLD}%s${C_RESET}\n\n" "${APP_NAME}"
}

main "$@"
