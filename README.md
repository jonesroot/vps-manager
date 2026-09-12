# VPS Manager Pro

Enterprise-grade, cross-platform interactive Terminal User Interface (TUI) for managing, monitoring, and orchestrating VPS fleets.

Powered by **Textual**, **AsyncSSH**, and **AES-256-GCM** authenticated encryption.

---

## Key Features

- **Pure AsyncSSH Engine**: 100% native across Linux, macOS, and Windows. Eliminates `sshpass` and prevents credential leakage in process tables (`ps aux`).
- **Modern Interactive TUI**: 60 FPS reactive UI with dark-theme styling, live resource gauges (CPU, RAM, Disk), and network latency badges.
- **Zero-Leak Security Vault**: Passwords and private key passphrases encrypted at-rest via `AES-256-GCM` with PBKDF2-HMAC-SHA256 (600,000 iterations).
- **Parallel Batch Execution**: Run shell commands across multiple servers simultaneously with live streaming log outputs and concurrency control.
- **Seamless Terminal Takeover**: Press `Enter` on any server to launch a full interactive native SSH session (`htop`, `vim`, `tmux`), returning cleanly to the TUI upon exit.
- **ACID-Compliant Storage**: Atomic file writes with advisory file locking (`fcntl` on POSIX / `msvcrt` on Windows) and auto-schema migration.

---

## Installation

Run the automated installer:

```bash
chmod +x install.sh
./install.sh
```

```markdown

---

## Keyboard Shortcuts & Navigation

| Key Binding | Action |
| :--- | :--- |
| `a` | **Add** a new server node configuration |
| `e` | **Edit** the currently highlighted server |
| `d` / `Delete` | **Delete** server with confirmation dialog |
| `Enter` | Launch full **interactive shell** session (terminal takeover) |
| `Space` | **Toggle selection** checkbox for batch operations |
| `b` | Launch **Parallel Batch Command Runner** on selected nodes |
| `r` | **Probe** active server connectivity and harvest metrics |
| `R` | Trigger full **fleet-wide refresh** in parallel |
| `/` | **Focus search** filter (filter by alias, host, group, tag) |
| `c` | **Clear** active filter and refocus table |
| `?` | Display **Help / Cheatsheet** modal |
| `q` / `Ctrl+C` | **Quit** VPS Manager |

---

## Configuration & Storage Paths

- **Linux**: `~/.config/vps_manager/servers.json`
- **macOS**: `~/Library/Application Support/vps_manager/servers.json`
- **Windows**: `%LOCALAPPDATA%\vps_manager\servers.json`

File permissions are strictly locked to `0600` (read/write by owner only).

---

## License

MIT License. Copyright (c) 2025 Elite Systems Architecture.
```

---
