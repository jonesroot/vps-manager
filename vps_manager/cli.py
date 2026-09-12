"""
vps_manager.cli
~~~~~~~~~~~~~~~

Command-Line Interface and application bootstrapping entrypoint.
Supports headless execution, backup operations, and TUI launching.

:copyright: (c) 2025 by Elite Systems Architecture.
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from vps_manager.version import __version__
from vps_manager.models import VPSManagerError
from vps_manager.security import FileSecurity, SecretVault
from vps_manager.storage import ServerRepository
from vps_manager.tui.app import VPSManagerApp


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
    """Main application execution pipeline."""
    if argv is None:
        argv = sys.argv[1:]

    parser = build_argument_parser()
    args = parser.parse_args(argv)

    # Initialize Security Vault & Storage
    try:
        vault = SecretVault.with_machine_key()
        repo = ServerRepository(storage_path=args.config, vault=vault)
    except VPSManagerError as exc:
        sys.stderr.write(f"\033[1;31mInitialization Failure: {exc}\033[0m\n")
        return 1

    # Route Subcommands
    if args.command == "export":
        try:
            repo.export_backup(args.target)
            print(f"\033[1;32m✔ Successfully exported backup to: {args.target}\033[0m")
            return 0
        except VPSManagerError as exc:
            sys.stderr.write(f"\033[1;31mExport failed: {exc}\033[0m\n")
            return 1

    if args.command == "import":
        try:
            count = repo.import_backup(args.source, merge=args.merge)
            mode = "merged" if args.merge else "imported"
            print(f"\033[1;32m✔ Successfully {mode} {count} servers from: {args.source}\033[0m")
            return 0
        except VPSManagerError as exc:
            sys.stderr.write(f"\033[1;31mImport failed: {exc}\033[0m\n")
            return 1

    # Default Action: Launch Modern Interactive TUI
    app = VPSManagerApp(storage_path=args.config, vault=vault)
    try:
        app.run()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        sys.stderr.write(f"\033[1;31mFatal Application Exception: {exc}\033[0m\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
