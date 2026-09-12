"""
vps_manager.tui.screens
~~~~~~~~~~~~~~~~~~~~~~~

Production modal dialog screens: Add/Edit Server forms, multi-node
batch command runner with streaming ANSI logs, and confirmation guards.

:copyright: (c) 2025 by Elite Systems Architecture.
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
import time
from typing import Final
from uuid import uuid4

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Select,
    Static,
)

from vps_manager.models import (
    AuthType,
    CommandResult,
    Server,
    ServerStatus,
    ValidationError,
)
from vps_manager.security import SecretVault
from vps_manager.ssh import SSHService


# ============================================================================
# SERVER CONFIGURATION MODAL (ADD / EDIT)
# ============================================================================


class ServerModalScreen(ModalScreen[Server | None]):
    """Modal screen for creating a new server or editing an existing one."""

    DEFAULT_CSS = """
    ServerModalScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.75);
    }
    #dialog-container {
        width: 80;
        height: 85%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        layout: vertical;
    }
    .modal-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
        height: 1;
    }
    #error-banner {
        color: $error;
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
        display: none;
    }
    #form-scroll {
        height: 1fr;
        scrollbar-size-vertical: 1;
        padding-right: 1;
    }
    .form-grid {
        grid-size: 2;
        grid-columns: 20 1fr;
        grid-rows: 3;
        grid-gutter: 1 0;
        height: auto;
    }
    .form-label {
        height: 3;
        content-align: left middle;
        text-style: bold;
        color: $text-muted;
    }
    .form-input {
        height: 3;
        width: 100%;
        color: $text;
        background: $boost;
    }
    .form-input:focus {
        border: tall $accent;
        color: $text;
    }
    .button-row {
        height: 4;
        align: right middle;
        border-top: solid $primary-muted;
        padding-top: 1;
        margin-top: 1;
    }
    .button-row Button {
        margin-left: 2;
        min-width: 16;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("ctrl+s", "save", "Save Server", priority=True),
    ]

    def __init__(
        self,
        server: Server | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._editing_server: Server | None = server

    def compose(self) -> ComposeResult:
        is_edit = self._editing_server is not None
        title_text = "EDIT SERVER NODE" if is_edit else "ADD NEW SERVER NODE"

        with Vertical(id="dialog-container"):
            yield Static(title_text, classes="modal-title", markup=False)
            yield Static("", id="error-banner", markup=False)

            with ScrollableContainer(id="form-scroll"):
                with Grid(classes="form-grid"):
                    # 1. Alias
                    yield Label("Alias / Name:", classes="form-label")
                    yield Input(
                        value=self._editing_server.alias if self._editing_server else "",
                        placeholder="e.g. prod-api-01",
                        id="input-alias",
                        classes="form-input",
                    )

                    # 2. Host
                    yield Label("Host / IP:", classes="form-label")
                    yield Input(
                        value=self._editing_server.host if self._editing_server else "",
                        placeholder="192.168.1.100 or vps.example.com",
                        id="input-host",
                        classes="form-input",
                    )

                    # 3. Port
                    yield Label("SSH Port:", classes="form-label")
                    yield Input(
                        value=str(self._editing_server.port) if self._editing_server else "22",
                        placeholder="22",
                        id="input-port",
                        classes="form-input",
                    )

                    # 4. Username
                    yield Label("SSH User:", classes="form-label")
                    yield Input(
                        value=self._editing_server.user if self._editing_server else "root",
                        placeholder="root",
                        id="input-user",
                        classes="form-input",
                    )

                    # 5. Auth Method Selection
                    yield Label("Auth Method:", classes="form-label")
                    auth_options: list[tuple[str, AuthType]] = [
                        ("Private Key File", AuthType.KEY_FILE),
                        ("Password", AuthType.PASSWORD),
                        ("SSH Agent", AuthType.AGENT),
                    ]
                    selected_auth = (
                        self._editing_server.auth_type if self._editing_server else AuthType.KEY_FILE
                    )
                    yield Select[AuthType](
                        options=auth_options,
                        value=selected_auth,
                        id="select-auth",
                        allow_blank=False,
                    )

                    # 6. Password Field (Shown when Auth == Password)
                    yield Label("Password:", id="label-password", classes="form-label")
                    yield Input(
                        value=self._editing_server.password if self._editing_server else "",
                        placeholder="SSH Password",
                        password=True,
                        id="input-password",
                        classes="form-input",
                    )

                    # 7. Private Key Path (Shown when Auth == Key File)
                    yield Label("Key File Path:", id="label-keypath", classes="form-label")
                    yield Input(
                        value=self._editing_server.key_path if self._editing_server else "~/.ssh/id_rsa",
                        placeholder="~/.ssh/id_ed25519",
                        id="input-keypath",
                        classes="form-input",
                    )

                    # 8. Key Passphrase
                    yield Label("Key Passphrase:", id="label-passphrase", classes="form-label")
                    yield Input(
                        value=self._editing_server.key_passphrase if self._editing_server else "",
                        placeholder="Optional key passphrase",
                        password=True,
                        id="input-passphrase",
                        classes="form-input",
                    )

                    # 9. Server Group
                    yield Label("Group / Env:", classes="form-label")
                    yield Input(
                        value=self._editing_server.group if self._editing_server else "Default",
                        placeholder="Production, Staging, DB",
                        id="input-group",
                        classes="form-input",
                    )

                    # 10. Tags
                    yield Label("Tags (CSV):", classes="form-label")
                    yield Input(
                        value=",".join(self._editing_server.tags) if self._editing_server else "",
                        placeholder="web, nginx, docker",
                        id="input-tags",
                        classes="form-input",
                    )

            # Permanent pinned bottom bar with visible Save and Cancel buttons
            with Horizontal(classes="button-row"):
                yield Button("✖ Cancel [Esc]", variant="default", id="btn-cancel")
                yield Button("💾 Save Server [Ctrl+S]", variant="primary", id="btn-save")

    def on_mount(self) -> None:
        """Synchronize field visibility with initial auth method and focus alias."""
        select_widget = self.query_one("#select-auth", Select)
        self._update_auth_fields(select_widget.value)
        self.query_one("#input-alias", Input).focus()

    @on(Select.Changed, "#select-auth")
    def handle_auth_changed(self, event: Select.Changed) -> None:
        """Toggle field visibility based on user selection."""
        if isinstance(event.value, AuthType):
            self._update_auth_fields(event.value)

    def _update_auth_fields(self, auth_type: AuthType | None) -> None:
        """Update visibility of authentication inputs."""
        lbl_pw = self.query_one("#label-password", Label)
        inp_pw = self.query_one("#input-password", Input)
        lbl_key = self.query_one("#label-keypath", Label)
        inp_key = self.query_one("#input-keypath", Input)
        lbl_pp = self.query_one("#label-passphrase", Label)
        inp_pp = self.query_one("#input-passphrase", Input)

        is_pw = auth_type == AuthType.PASSWORD
        is_key = auth_type == AuthType.KEY_FILE

        lbl_pw.display = is_pw
        inp_pw.display = is_pw

        lbl_key.display = is_key
        inp_key.display = is_key
        lbl_pp.display = is_key
        inp_pp.display = is_key

    @on(Button.Pressed, "#btn-cancel")
    def action_cancel(self) -> None:
        """Dismiss modal without making changes."""
        self.dismiss(None)

    @on(Button.Pressed, "#btn-save")
    def action_save(self) -> None:
        """Validate input invariants and dismiss with updated/new Server."""
        err_banner = self.query_one("#error-banner", Static)
        err_banner.display = False

        alias_val = self.query_one("#input-alias", Input).value.strip()
        host_val = self.query_one("#input-host", Input).value.strip()
        port_raw = self.query_one("#input-port", Input).value.strip()
        user_val = self.query_one("#input-user", Input).value.strip()

        # Pre-validate mandatory fields with immediate auto-focus
        if not alias_val:
            self._show_error("Server alias cannot be empty.")
            self.query_one("#input-alias", Input).focus()
            return

        if not host_val:
            self._show_error("Server host cannot be empty.")
            self.query_one("#input-host", Input).focus()
            return

        select_auth = self.query_one("#select-auth", Select)
        auth_type: AuthType = (
            select_auth.value if isinstance(select_auth.value, AuthType) else AuthType.KEY_FILE
        )

        password_val = self.query_one("#input-password", Input).value
        key_path_val = self.query_one("#input-keypath", Input).value.strip()
        passphrase_val = self.query_one("#input-passphrase", Input).value
        group_val = self.query_one("#input-group", Input).value.strip() or "Default"
        tags_raw = self.query_one("#input-tags", Input).value

        # Parse port safely
        try:
            port_val = int(port_raw)
            if not (1 <= port_val <= 65535):
                self._show_error("Port must be between 1 and 65535.")
                self.query_one("#input-port", Input).focus()
                return
        except ValueError:
            self._show_error("Port must be a valid integer between 1 and 65535.")
            self.query_one("#input-port", Input).focus()
            return

        # Parse tags
        tags_tuple: tuple[str, ...] = tuple(t.strip().lower() for t in tags_raw.split(",") if t.strip())

        # Safely determine server ID and status without dummy instantiation
        server_id = self._editing_server.id if self._editing_server else uuid4().hex
        server_status = self._editing_server.status if self._editing_server else ServerStatus.UNCHECKED

        try:
            new_server = Server(
                id=server_id,
                alias=alias_val,
                host=host_val,
                port=port_val,
                user=user_val,
                auth_type=auth_type,
                password=password_val if auth_type == AuthType.PASSWORD else None,
                key_path=key_path_val if auth_type == AuthType.KEY_FILE else None,
                key_passphrase=passphrase_val if auth_type == AuthType.KEY_FILE and passphrase_val else None,
                group=group_val,
                tags=tags_tuple,
                status=server_status,
                latency_ms=self._editing_server.latency_ms if self._editing_server else None,
                metrics=self._editing_server.metrics if self._editing_server else None,
            )
            self.dismiss(new_server)
        except ValidationError as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        err_banner = self.query_one("#error-banner", Static)
        err_banner.update(f"▲ {message}")
        err_banner.display = True


# ============================================================================
# BATCH MULTI-SERVER COMMAND RUNNER MODAL
# ============================================================================


class BatchCommandRunnerScreen(ModalScreen[None]):
    """Modal screen for executing remote commands simultaneously across multiple servers."""

    DEFAULT_CSS = """
    BatchCommandRunnerScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }
    #batch-container {
        width: 90%;
        height: 85%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    .batch-title {
        text-style: bold;
        color: $accent;
        text-align: center;
        margin-bottom: 1;
    }
    #target-info {
        height: 1;
        color: $text-muted;
        margin-bottom: 1;
    }
    .cmd-row {
        height: 3;
        layout: horizontal;
        margin-bottom: 1;
    }
    #input-batch-cmd {
        width: 1fr;
        height: 3;
        color: $text;
        background: $boost;
    }
    #btn-run-batch {
        width: 16;
        height: 3;
        margin-left: 1;
    }
    #batch-progress {
        width: 100%;
        margin-bottom: 1;
        display: none;
    }
    #batch-log {
        height: 1fr;
        border: solid $primary-muted;
        background: $background;
        margin-bottom: 1;
    }
    .batch-footer {
        height: 3;
        align: right middle;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", priority=True),
    ]

    def __init__(
        self,
        target_servers: Sequence[Server],
        vault: SecretVault | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._target_servers: Final[tuple[Server, ...]] = tuple(target_servers)
        self._vault: Final[SecretVault | None] = vault
        self._is_running: bool = False

    def compose(self) -> ComposeResult:
        server_aliases = ", ".join(s.alias for s in self._target_servers)
        with Vertical(id="batch-container"):
            yield Static("PARALLEL BATCH COMMAND RUNNER", classes="batch-title", markup=False)
            yield Static(
                f"Targets ({len(self._target_servers)} nodes): [bold cyan]{server_aliases}[/]",
                id="target-info",
                markup=True,
            )

            with Horizontal(classes="cmd-row"):
                yield Input(
                    placeholder="Enter shell command (e.g. uptime, docker ps, apt update)...",
                    id="input-batch-cmd",
                )
                yield Button("Execute [Enter]", variant="success", id="btn-run-batch")

            yield ProgressBar(total=len(self._target_servers), id="batch-progress", show_eta=False)
            yield RichLog(id="batch-log", highlight=True, markup=True, wrap=True)

            with Horizontal(classes="batch-footer"):
                yield Button("Close [Esc]", variant="default", id="btn-close-batch")

    @on(Button.Pressed, "#btn-close-batch")
    def action_dismiss_modal(self) -> None:
        if not self._is_running:
            self.dismiss(None)

    @on(Button.Pressed, "#btn-run-batch")
    @on(Input.Submitted, "#input-batch-cmd")
    def action_execute_batch(self) -> None:
        cmd = self.query_one("#input-batch-cmd", Input).value.strip()
        if not cmd or self._is_running:
            return

        self._is_running = True
        self.query_one("#btn-run-batch", Button).disabled = True
        self.query_one("#input-batch-cmd", Input).disabled = True
        self.query_one("#btn-close-batch", Button).disabled = True

        progress = self.query_one("#batch-progress", ProgressBar)
        progress.progress = 0
        progress.display = True

        log = self.query_one("#batch-log", RichLog)
        log.clear()
        log.write(Text(f"▶ Launching batch execution across {len(self._target_servers)} servers...", style="bold yellow"))
        log.write(Text(f"Command: {cmd}\n", style="dim white"))

        self.run_worker(self._run_batch_worker(cmd))

    async def _run_batch_worker(self, command: str) -> None:
        """Worker coroutine distributing commands across servers with controlled concurrency."""
        log = self.query_one("#batch-log", RichLog)
        progress = self.query_one("#batch-progress", ProgressBar)
        semaphore = asyncio.Semaphore(10)

        async def _exec_single(server: Server) -> CommandResult:
            async with semaphore:
                log.write(Text(f"[{server.alias}] Connecting...", style="dim cyan"))
                result = await SSHService.execute_command(server, command, timeout=45.0, vault=self._vault)

                status_color = "bold green" if result.success else "bold red"
                log.write(Text(f"[{server.alias}] Done in {result.duration_seconds}s (exit {result.exit_code})", style=status_color))

                if result.stdout.strip():
                    for line in result.stdout.splitlines():
                        t_out = Text()
                        t_out.append(f"  [{server.alias}] ", style="dim cyan")
                        t_out.append(line)
                        log.write(t_out)

                if result.stderr.strip():
                    for line in result.stderr.splitlines():
                        t_err = Text()
                        t_err.append(f"  [{server.alias}] ", style="dim cyan")
                        t_err.append(line, style="red")
                        log.write(t_err)

                progress.advance(1)
                return result

        tasks = [_exec_single(s) for s in self._target_servers]
        t0 = time.monotonic()
        results = await asyncio.gather(*tasks, return_exceptions=False)
        total_time = time.monotonic() - t0

        succeeded = sum(1 for r in results if r.success)
        failed = len(results) - succeeded

        log.write(Text(f"\n✔ Batch finished in {total_time:.2f}s. Success: {succeeded}, Failed: {failed}", style="bold white"))

        self._is_running = False
        self.query_one("#btn-run-batch", Button).disabled = False
        self.query_one("#input-batch-cmd", Input).disabled = False
        self.query_one("#btn-close-batch", Button).disabled = False


# ============================================================================
# CONFIRMATION DIALOG MODAL
# ============================================================================


class ConfirmDialogModal(ModalScreen[bool]):
    """Generic modal dialog verifying irreversible destructive actions."""

    DEFAULT_CSS = """
    ConfirmDialogModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.75);
    }
    #confirm-container {
        width: 54;
        height: auto;
        background: $surface;
        border: thick $error;
        padding: 1 2;
    }
    #confirm-title {
        text-style: bold;
        color: $error;
        text-align: center;
        margin-bottom: 1;
    }
    #confirm-message {
        text-align: center;
        margin-bottom: 1;
    }
    .confirm-buttons {
        height: 3;
        align: center middle;
    }
    .confirm-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("enter", "confirm", "Confirm", priority=True),
    ]

    def __init__(
        self,
        title: str,
        message: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._title_text: Final[str] = title
        self._message_text: Final[str] = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-container"):
            yield Static(self._title_text, id="confirm-title", markup=False)
            yield Static(self._message_text, id="confirm-message", markup=False)
            with Horizontal(classes="confirm-buttons"):
                yield Button("Cancel [Esc]", variant="default", id="btn-cancel-action")
                yield Button("Delete [Enter]", variant="error", id="btn-confirm-action")

    @on(Button.Pressed, "#btn-cancel-action")
    def action_cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#btn-confirm-action")
    def action_confirm(self) -> None:
        self.dismiss(True)


# ============================================================================
# KEYBOARD SHORTCUTS HELP MODAL
# ============================================================================


class HelpScreen(ModalScreen[None]):
    """Visual keyboard navigation and shortcut reference cheatsheet."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.75);
    }
    #help-container {
        width: 64;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    .help-title {
        text-style: bold;
        color: $accent;
        text-align: center;
        margin-bottom: 1;
    }
    .help-table {
        margin-bottom: 1;
    }
    .help-row {
        height: 1;
    }
    .help-key {
        width: 14;
        text-style: bold;
        color: $primary;
    }
    .help-desc {
        width: 1fr;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("escape,enter,space,q", "close", "Close", priority=True),
    ]

    SHORTCUTS: Final[tuple[tuple[str, str], ...]] = (
        ("a", "Add new server configuration"),
        ("e", "Edit focused server parameters"),
        ("d / Delete", "Delete focused server permanently"),
        ("Enter", "Launch full interactive terminal (pty takeover)"),
        ("Space", "Toggle server selection for batch execution"),
        ("b", "Open Batch Command Runner on selected servers"),
        ("r", "Probe active server connection and metrics"),
        ("R", "Refresh entire fleet telemetry in background"),
        ("/", "Focus search bar (filter by alias, host, tag)"),
        ("c", "Clear active search filter"),
        ("?", "Open this Help / Keymap reference"),
        ("q / Ctrl+C", "Gracefully exit VPS Manager"),
    )

    def compose(self) -> ComposeResult:
        with Vertical(id="help-container"):
            yield Static("KEYBOARD CHEATSHEET & NAVIGATION", classes="help-title", markup=False)
            with Vertical(classes="help-table"):
                for key_combo, desc in self.SHORTCUTS:
                    with Horizontal(classes="help-row"):
                        yield Static(f"[{key_combo}]", classes="help-key", markup=False)
                        yield Static(desc, classes="help-desc", markup=False)
            yield Button("Close [Esc]", variant="primary", id="btn-close-help")

    @on(Button.Pressed, "#btn-close-help")
    def action_close(self) -> None:
        self.dismiss(None)
