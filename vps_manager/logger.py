"""
vps_manager.logger
~~~~~~~~~~~~~~~~~~

Production-grade centralized error logging and automated exception trapping.
Automatically intercepts uncaught synchronous, multithreaded, and asynchronous
exceptions and logs them into 'log_error.txt' located at the repository root
and the user configuration directory.

:copyright: (c) 2025 by Elite Systems Architecture.
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import re
import sys
import threading
import traceback
from types import TracebackType
from typing import Final

from vps_manager.version import __version__


# ============================================================================
# CONSTANTS & METADATA
# ============================================================================

LOG_FILENAME: Final[str] = "log_error.txt"

# Thread-safety lock to prevent interleaved log writes
_LOG_LOCK: Final[threading.Lock] = threading.Lock()

# Sanitization regex patterns to eliminate credential exposure in log files
_SANITIZE_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"enc:v1:[A-Za-z0-9_-]+:[A-Za-z0-9_-]+"), "enc:v1:[REDACTED_VAULT_TOKEN]"),
    (re.compile(r"(password['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])", re.IGNORECASE), r"\1***REDACTED***\3"),
    (re.compile(r"(key_passphrase['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])", re.IGNORECASE), r"\1***REDACTED***\3"),
    (re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[^-]+-----END [A-Z ]+ PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY_BLOCK]"),
)


# ============================================================================
# REPOSITORY ROOT & LOG DESTINATIONS DISCOVERY
# ============================================================================


def get_repository_root() -> Path:
    """Deterministically locate the repository root or active working directory.

    1. Checks if current working directory (Path.cwd()) contains project sentinels.
    2. Searches upward from the module path for sentinels ('pyproject.toml', '.git', 'README.md').
    3. Defaults to Path.cwd() if running from installed package environment.
    """
    cwd = Path.cwd().resolve()
    if (cwd / "pyproject.toml").exists() or (cwd / ".git").exists() or (cwd / "README.md").exists():
        return cwd

    current_path = Path(__file__).resolve()
    for parent in (current_path.parent, *current_path.parents):
        if (
            (parent / "pyproject.toml").exists()
            or (parent / ".git").exists()
            or (parent / "README.md").exists()
        ):
            return parent

    return cwd


def get_error_log_path() -> Path:
    """Return primary absolute canonical path to log_error.txt at repository root."""
    return get_repository_root() / LOG_FILENAME


def get_fallback_log_path() -> Path:
    """Return secondary fallback log path in the user config directory."""
    home = Path.home()
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA")
        base = Path(local_appdata) if local_appdata else home / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else home / ".config"

    config_dir = base / "vps_manager"
    return config_dir / LOG_FILENAME


# ============================================================================
# SANITIZATION UTILITIES
# ============================================================================


def sanitize_log_message(message: str) -> str:
    """Scrub sensitive credentials, vault tokens, and private keys from log content."""
    sanitized = message
    for pattern, replacement in _SANITIZE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


# ============================================================================
# CORE ERROR LOGGING PIPELINE
# ============================================================================


def log_error(
    error: BaseException | str,
    *,
    context: str = "",
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None = None,
) -> None:
    """Record a detailed, timestamped error entry into 'log_error.txt'.

    Writes to the primary repository root destination and mirrors to the config
    fallback path. Outputs the exact absolute path to sys.stderr.

    Thread-safe and process-safe. Never raises uncaught exceptions.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    primary_log_file = get_error_log_path()
    fallback_log_file = get_fallback_log_path()

    # Extract exception details and traceback
    if isinstance(error, BaseException):
        err_type = type(error).__name__
        err_msg = str(error)
        tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
        tb_str = "".join(tb_lines).strip()
    elif exc_info is not None:
        err_type = exc_info[0].__name__
        err_msg = str(exc_info[1])
        tb_lines = traceback.format_exception(*exc_info)
        tb_str = "".join(tb_lines).strip()
    else:
        err_type = "ExplicitLogMessage"
        err_msg = str(error)
        tb_str = "".join(traceback.format_stack()[:-1]).strip()

    # Sanitize content
    sanitized_msg = sanitize_log_message(err_msg)
    sanitized_tb = sanitize_log_message(tb_str)
    sanitized_ctx = sanitize_log_message(context) if context else "None specified"

    # Construct formatted log block
    separator = "=" * 80
    sub_sep = "-" * 80
    header = (
        f"{separator}\n"
        f"TIMESTAMP   : {timestamp}\n"
        f"VERSION     : {__version__}\n"
        f"PLATFORM    : {platform.system()} {platform.release()} ({platform.machine()})\n"
        f"PYTHON      : {platform.python_implementation()} {platform.python_version()}\n"
        f"PID / THREAD: {os.getpid()} / {threading.current_thread().name}\n"
        f"CONTEXT     : {sanitized_ctx}\n"
        f"ERROR TYPE  : {err_type}\n"
        f"MESSAGE     : {sanitized_msg}\n"
        f"{sub_sep}\n"
        f"TRACEBACK   :\n"
        f"{sanitized_tb}\n"
        f"{separator}\n\n"
    )

    written_paths: list[Path] = []

    # Thread-safe atomic file append
    with _LOG_LOCK:
        # 1. Attempt write to primary path
        try:
            primary_log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(primary_log_file, "a", encoding="utf-8", errors="replace") as f:
                f.write(header)
                f.flush()
            written_paths.append(primary_log_file)
        except OSError:
            pass

        # 2. Attempt write to fallback config path if different
        if fallback_log_file != primary_log_file:
            try:
                fallback_log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(fallback_log_file, "a", encoding="utf-8", errors="replace") as f:
                    f.write(header)
                    f.flush()
                written_paths.append(fallback_log_file)
            except OSError:
                pass

    # Print clear terminal diagnostic notice
    if written_paths:
        sys.stderr.write(f"\n\033[1;31m[CRASH DETECTED]\033[0m Logged to:\n")
        for p in written_paths:
            sys.stderr.write(f"  \033[1;33m➜ {p.resolve()}\033[0m\n")
    else:
        sys.stderr.write("\033[1;31m[CRITICAL]: Failed writing log_error.txt to disk. Dumping to stderr:\033[0m\n")
        sys.stderr.write(header)


# ============================================================================
# GLOBAL EXCEPTION TRAPPING HOOKS
# ============================================================================


def _global_sys_excepthook(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
) -> None:
    """Intercept all uncaught synchronous exceptions in the main thread."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    log_error(
        exc_value,
        context="Uncaught Main Thread Exception",
        exc_info=(exc_type, exc_value, exc_traceback),
    )
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def _global_threading_excepthook(args: threading.ExceptHookArgs) -> None:
    """Intercept all uncaught exceptions in background threads."""
    if args.exc_type is not None and issubclass(args.exc_type, KeyboardInterrupt):
        return

    thread_name = args.thread.name if args.thread else "UnknownThread"
    exc_val = args.exc_value if args.exc_value is not None else RuntimeError("Thread crash with no exception value")
    log_error(
        exc_val,
        context=f"Uncaught Worker Thread Exception [{thread_name}]",
        exc_info=(args.exc_type, exc_val, args.exc_traceback) if args.exc_type else None,
    )


def _global_asyncio_exception_handler(
    loop: asyncio.AbstractEventLoop,
    context: dict[str, object],
) -> None:
    """Intercept unhandled exceptions inside background asyncio coroutines/tasks."""
    exc = context.get("exception")
    message = context.get("message", "Unhandled event loop anomaly")

    if isinstance(exc, BaseException):
        if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)):
            return
        log_error(
            exc,
            context=f"Unhandled AsyncIO Task Exception: {message}",
        )
    else:
        log_error(
            str(message),
            context=f"AsyncIO Loop Diagnostic: {context}",
        )

    loop.default_exception_handler(context)


def setup_error_logger(custom_root: Path | None = None) -> Path:
    """Install global exception hooks to automatically write crashes to log_error.txt.

    Registers:
    1. sys.excepthook (Main thread synchronous crashes)
    2. threading.excepthook (Multithreaded background worker crashes)

    Returns:
        Canonical Path to the active log_error.txt destination.
    """
    target_path = (custom_root / LOG_FILENAME) if custom_root else get_error_log_path()

    sys.excepthook = _global_sys_excepthook
    threading.excepthook = _global_threading_excepthook

    return target_path


def attach_asyncio_loop_error_handler(loop: asyncio.AbstractEventLoop | None = None) -> None:
    """Attach the asynchronous exception handler to an active asyncio event loop."""
    active_loop = loop if loop is not None else asyncio.get_event_loop()
    active_loop.set_exception_handler(_global_asyncio_exception_handler)
