"""
vps_manager.cli
~~~~~~~~~~~~~~~

Command-Line Interface and application bootstrapping entrypoint.
Supports headless execution, backup operations, automated crash logging,
and interactive TUI launching.

:copyright: (c) 2025 by Elite Systems Architecture.
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from vps_manager.logger import get_error_log_path, log_error, setup_error_logger
from vps_manager.models import VPSManagerError
from vps_manager.security import SecretVault
from vps_manager.storage import ServerRepository
from vps_manager.tui.app import VPSManagerApp
from vps_manager.version import __version__


def build_argument_parser() -> argparse.ArgumentParser:
    """Construct standard CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="vps-manager",
        description="VPS Manager Pro: Modern, cross-platform interactive TUI & orchestration suite.",
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show program version and exit.",
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=None,
        help="Path to custom servers.json configuration file.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Operational subcommands")

    # Subcommand: Backup Export
    export_parser = subparsers.add_parser("export", help="Export server database to a JSON archive.")
    export_parser.add_argument("target", type=Path, help="Target file path for the backup JSON.")

    # Subcommand: Backup Import
    import_parser = subparsers.add_parser("import", help="Import servers from a JSON archive.")
    import_parser.add_argument("source", type=Path, help="Source JSON archive path.")
    import_parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge imported nodes with existing database instead of overwriting.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main application execution pipeline with automated crash logging."""
    # 1. Install global exception traps immediately upon entry
    log_file_path = setup_error_logger()

    if argv is None:
        argv = sys.argv[1:]

    parser = build_argument_parser()
    args = parser.parse_args(argv)

    # Safely extract and narrow arguments for Pyright strict compliance
    config_arg = getattr(args, "config", None)
    config_path: Path | None = config_arg if isinstance(config_arg, Path) else None

    command_arg = getattr(args, "command", None)
    command: str | None = command_arg if isinstance(command_arg, str) else None

    # 2. Initialize Security Vault & Storage
    try:
        vault = SecretVault.with_machine_key()
        repo = ServerRepository(storage_path=config_path, vault=vault)
    except Exception as exc:
        log_error(exc, context="Vault or Repository Bootstrapping Failure")
        sys.stderr.write(f"\033[1;31mInitialization Failure: {exc}\033[0m\n")
        sys.stderr.write(f"\033[1;33m[!] Crash details appended to: {log_file_path}\033[0m\n")
        return 1

    # 3. Route Operational Subcommands
    if command == "export":
        target_arg = getattr(args, "target", None)
        if not isinstance(target_arg, Path):
            err_msg = "Export failed: missing target file path."
            log_error(err_msg, context="CLI Subcommand Validation")
            sys.stderr.write(f"\033[1;31m{err_msg}\033[0m\n")
            return 1

        try:
            repo.export_backup(target_arg)
            print(f"\033[1;32m✔ Successfully exported backup to: {target_arg}\033[0m")
            return 0
        except VPSManagerError as exc:
            log_error(exc, context=f"Database Export to '{target_arg}'")
            sys.stderr.write(f"\033[1;31mExport failed: {exc}\033[0m\n")
            sys.stderr.write(f"\033[1;33m[!] Details saved to: {log_file_path}\033[0m\n")
            return 1

    if command == "import":
        source_arg = getattr(args, "source", None)
        if not isinstance(source_arg, Path):
            err_msg = "Import failed: missing source file path."
            log_error(err_msg, context="CLI Subcommand Validation")
            sys.stderr.write(f"\033[1;31m{err_msg}\033[0m\n")
            return 1

        merge_flag: bool = bool(getattr(args, "merge", False))
        try:
            count = repo.import_backup(source_arg, merge=merge_flag)
            mode = "merged" if merge_flag else "imported"
            print(f"\033[1;32m✔ Successfully {mode} {count} servers from: {source_arg}\033[0m")
            return 0
        except VPSManagerError as exc:
            log_error(exc, context=f"Database Import from '{source_arg}' (merge={merge_flag})")
            sys.stderr.write(f"\033[1;31mImport failed: {exc}\033[0m\n")
            sys.stderr.write(f"\033[1;33m[!] Details saved to: {log_file_path}\033[0m\n")
            return 1

    # 4. Default Action: Launch Interactive TUI Application
    app = VPSManagerApp(storage_path=config_path, vault=vault)
    try:
        app.run()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        log_error(exc, context="Fatal Textual TUI Runtime Exception")
        sys.stderr.write(f"\033[1;31mFatal Application Exception: {exc}\033[0m\n")
        sys.stderr.write(f"\033[1;33m[!] Comprehensive crash report written to: {log_file_path}\033[0m\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
