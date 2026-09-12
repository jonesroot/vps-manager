"""
vps_manager.tui.app
~~~~~~~~~~~~~~~~~~~

Main Textual Application orchestrator for VPS Manager.
Manages application lifecycle, terminal suspension, reactive filtering,
asynchronous telemetry polling, and automated crash interception.

:copyright: (c) 2025 by Elite Systems Architecture.
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import sys
import time
from typing import Final

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.widgets import Button, DataTable, Footer, Header, Input, Static

from vps_manager.logger import log_error
from vps_manager.models import Server
from vps_manager.security import SecretVault
from vps_manager.ssh import SSHService
from vps_manager.storage import ServerNotFoundError, ServerRepository
from vps_manager.tui.screens import (
    BatchCommandRunnerScreen,
    ConfirmDialogModal,
    HelpScreen,
    ServerModalScreen,
)
from vps_manager.tui.widgets import (
    FleetSummaryBar,
    ServerDataTable,
    ServerTelemetryCard,
)


class VPSManagerApp(App[None]):
    """Enterprise Interactive TUI Application for managing VPS fleets."""

    TITLE = "VPS MANAGER PRO"
    SUB_TITLE = "Fleet Orchestrator & Telemetry"

    CSS = """
    Screen {
        layout: vertical;
        background: $background;
    }
    #action-bar {
        height: 3;
        padding: 0 1;
        background: $surface;
        layout: horizontal;
        align: left middle;
        border-bottom: solid $primary-muted;
    }
    #action-bar Button {
        height: 1;
        border: none;
        margin-right: 1;
        padding: 0 1;
        min-width: 11;
        text-style: bold;
    }
    #search-container {
        height: 3;
        padding: 0 1;
        background: $surface;
    }
    #search-input {
        width: 100%;
    }
    #main-content {
        height: 1fr;
        layout: horizontal;
    }
    #table-container {
        width: 65%;
        height: 100%;
        padding: 0 1;
    }
    #empty-notice {
        width: 100%;
        height: 100%;
        align: center middle;
        border: round $primary-muted;
        background: $surface;
        padding: 2;
    }
    #empty-notice-text {
        text-align: center;
        margin-bottom: 1;
    }
    #inspector-container {
        width: 35%;
        height: 100%;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("enter", "connect_terminal", "Shell", show=True),
        Binding("a", "add_server", "Add", show=True),
        Binding("e", "edit_server", "Edit", show=True),
        Binding("d", "delete_server", "Del", show=True),
        Binding("space", "toggle_selection", "Select", show=True),
        Binding("b", "batch_exec", "Batch", show=True),
        Binding("r", "refresh_active", "Probe", show=True),
        Binding("R", "refresh_fleet", "Fleet", show=True),
        Binding("slash", "focus_search", "Search [/]", show=True),
        Binding("c", "clear_search", "Clear", show=False),
        Binding("question_mark", "show_help", "Help", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        storage_path: Path | None = None,
        vault: SecretVault | None = None,
    ) -> None:
        super().__init__()
        self._vault: Final[SecretVault] = (
            vault if vault is not None else SecretVault.with_machine_key()
        )
        self._repository: Final[ServerRepository] = ServerRepository(
            storage_path=storage_path,
            vault=self._vault,
        )
        self._all_servers: list[Server] = []
        self._active_filter: str = ""
        self._polling_active: bool = False

    def _handle_exception(self, error: Exception) -> None:
        """Intercept all internal Textual runtime, layout, and rendering exceptions."""
        log_error(error, context="Textual TUI Internal Runtime Exception")
        super()._handle_exception(error)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield FleetSummaryBar(id="fleet-summary")

        with Horizontal(id="action-bar"):
            yield Button("▶ Connect [Enter]", variant="success", id="btn-quick-connect")
            yield Button("+ Add [a]", variant="primary", id="btn-quick-add")
            yield Button("✏ Edit [e]", variant="default", id="btn-quick-edit")
            yield Button("🗑 Del [d]", variant="error", id="btn-quick-delete")
            yield Button("⚡ Batch [b]", variant="warning", id="btn-quick-batch")
            yield Button("🔄 Fleet [R]", variant="default", id="btn-quick-refresh")
            yield Button("❓ Help [?]", variant="default", id="btn-quick-help")

        with Horizontal(id="search-container"):
            yield Input(
                placeholder="Search by alias, host, group, tag... (Press '/' to search, 'Esc' to return to table)",
                id="search-input",
            )

        with Horizontal(id="main-content"):
            with Vertical(id="table-container"):
                yield ServerDataTable(id="server-table")
                with Vertical(id="empty-notice"):
                    yield Static(
                        "[bold cyan]NO SERVERS CONFIGURED YET[/bold cyan]\n\n"
                        "[dim]Your VPS fleet list is currently empty.\n"
                        "Add your first server node to start monitoring and orchestration.[/dim]\n",
                        id="empty-notice-text",
                    )
                    yield Button("+ Add Your First Server [a]", variant="primary", id="btn-empty-add")
            with Vertical(id="inspector-container"):
                yield ServerTelemetryCard(id="server-inspector")

        yield Footer()

    async def on_mount(self) -> None:
        self.reload_servers_from_storage()
        table = self.query_one("#server-table", ServerDataTable)
        if len(self._all_servers) > 0:
            table.focus()
        else:
            self.query_one("#btn-empty-add", Button).focus()

        self.run_worker(self._probe_fleet_worker(fetch_metrics=True))
        self.set_interval(60.0, self._scheduled_fleet_refresh)

    def reload_servers_from_storage(self) -> None:
        self._all_servers = self._repository.list_all()
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self._active_filter.strip().lower()
        if not query:
            filtered = self._all_servers
        else:
            filtered = [
                s
                for s in self._all_servers
                if query in s.alias.lower()
                or query in s.host.lower()
                or query in s.group.lower()
                or any(query in tag.lower() for tag in s.tags)
            ]

        table = self.query_one("#server-table", ServerDataTable)
        empty_notice = self.query_one("#empty-notice", Vertical)

        if len(self._all_servers) == 0:
            table.display = False
            empty_notice.display = True
        else:
            table.display = True
            empty_notice.display = False
            table.populate_servers(filtered)

        summary = self.query_one("#fleet-summary", FleetSummaryBar)
        summary.update_from_servers(self._all_servers)
        self._sync_inspector_with_cursor()

    def _get_focused_server(self) -> Server | None:
        """Resolve currently highlighted server with multiple fallback strategies."""
        table = self.query_one("#server-table", ServerDataTable)
        if table.row_count == 0:
            return None

        # Strategy 1: Direct lookup via cursor row index and ordered IDs
        if 0 <= table.cursor_row < len(table._ordered_ids):
            target_id = table._ordered_ids[table.cursor_row]
            for s in self._all_servers:
                if s.id == target_id:
                    return s

        # Strategy 2: Cell coordinate key resolution
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
            server_id = row_key.value
            if server_id:
                for s in self._all_servers:
                    if s.id == server_id:
                        return s
        except Exception:
            pass

        # Strategy 3: Single server fleet fallback
        if len(self._all_servers) == 1:
            return self._all_servers[0]

        return None

    def _sync_inspector_with_cursor(self) -> None:
        inspector = self.query_one("#server-inspector", ServerTelemetryCard)
        inspector.server = self._get_focused_server()

    @on(Input.Changed, "#search-input")
    def handle_search_changed(self, event: Input.Changed) -> None:
        self._active_filter = event.value
        self._apply_filter()

    @on(Input.Submitted, "#search-input")
    def handle_search_submitted(self) -> None:
        self.query_one("#server-table", ServerDataTable).focus()

    @on(Key)
    def handle_key_events(self, event: Key) -> None:
        """Handle escape key when inside search input to return focus to table."""
        if event.key == "escape":
            search_input = self.query_one("#search-input", Input)
            if search_input.has_focus:
                self.query_one("#server-table", ServerDataTable).focus()
                event.stop()

    @on(DataTable.RowHighlighted, "#server-table")
    def handle_row_highlighted(self) -> None:
        self._sync_inspector_with_cursor()

    @on(DataTable.RowSelected, "#server-table")
    def handle_row_selected(self) -> None:
        """Trigger interactive SSH terminal session when Enter is pressed on table row."""
        self.action_connect_terminal()

    @on(Button.Pressed, "#btn-quick-connect")
    @on(Button.Pressed, "#btn-card-connect")
    def on_click_connect(self) -> None:
        self.action_connect_terminal()

    @on(Button.Pressed, "#btn-quick-add")
    @on(Button.Pressed, "#btn-empty-add")
    def on_click_add(self) -> None:
        self.action_add_server()

    @on(Button.Pressed, "#btn-quick-edit")
    def on_click_edit(self) -> None:
        self.action_edit_server()

    @on(Button.Pressed, "#btn-quick-delete")
    def on_click_delete(self) -> None:
        self.action_delete_server()

    @on(Button.Pressed, "#btn-quick-batch")
    def on_click_batch(self) -> None:
        self.action_batch_exec()

    @on(Button.Pressed, "#btn-quick-refresh")
    def on_click_refresh(self) -> None:
        self.action_refresh_fleet()

    @on(Button.Pressed, "#btn-quick-help")
    def on_click_help(self) -> None:
        self.action_show_help()

    def action_focus_search(self) -> None:
        inp = self.query_one("#search-input", Input)
        inp.focus()

    def action_clear_search(self) -> None:
        inp = self.query_one("#search-input", Input)
        inp.value = ""
        self._active_filter = ""
        self._apply_filter()
        self.query_one("#server-table", ServerDataTable).focus()

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_add_server(self) -> None:
        def _on_add_done(result: Server | None) -> None:
            if result is not None:
                self._repository.add(result)
                self.reload_servers_from_storage()
                self.run_worker(self._probe_single_server_worker(result))

        self.push_screen(ServerModalScreen(), _on_add_done)

    def action_edit_server(self) -> None:
        server = self._get_focused_server()
        if server is None:
            return

        def _on_edit_done(result: Server | None) -> None:
            if result is not None:
                self._repository.update(result)
                self.reload_servers_from_storage()
                self.run_worker(self._probe_single_server_worker(result))

        self.push_screen(ServerModalScreen(server=server), _on_edit_done)

    def action_delete_server(self) -> None:
        server = self._get_focused_server()
        if server is None:
            return

        def _on_confirm(confirmed: bool) -> None:
            if confirmed:
                try:
                    self._repository.delete(server.id)
                    self.reload_servers_from_storage()
                except ServerNotFoundError:
                    pass

        self.push_screen(
            ConfirmDialogModal(
                title="DELETE SERVER NODE",
                message=f"Are you sure you want to permanently delete '{server.alias}' ({server.host})?",
            ),
            _on_confirm,
        )

    def action_toggle_selection(self) -> None:
        server = self._get_focused_server()
        if server:
            table = self.query_one("#server-table", ServerDataTable)
            table.toggle_selection(server.id)

    def action_batch_exec(self) -> None:
        table = self.query_one("#server-table", ServerDataTable)
        selected_ids = table.get_selected_server_ids()

        target_servers = [s for s in self._all_servers if s.id in selected_ids]
        if not target_servers:
            focused = self._get_focused_server()
            if focused:
                target_servers = [focused]
            else:
                return

        self.push_screen(
            BatchCommandRunnerScreen(
                target_servers=target_servers, vault=self._vault
            )
        )

    def action_connect_terminal(self) -> None:
        """Launch native OpenSSH interactive shell by suspending Textual TUI."""
        server = self._get_focused_server()
        if server is None:
            return

        cmd = SSHService.build_native_cli_command(server, vault=self._vault)

        with self.suspend():
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
            print("\033[1;36m" + "=" * 70)
            print(f" VPS MANAGER PRO :: ATTACHING INTERACTIVE TERMINAL SESSION")
            print(f" Target Node : {server.alias} ({server.user}@{server.host}:{server.port})")
            print("=" * 70 + "\033[0m\n")

            try:
                subprocess.run(cmd)
            except KeyboardInterrupt:
                pass
            except Exception as exc:
                print(f"\n\033[1;31mSession ended with error: {exc}\033[0m")
                time.sleep(2.0)

            print("\n\033[1;33mReturning to VPS Manager TUI...\033[0m")
            time.sleep(0.5)

        self.refresh()

    def action_refresh_active(self) -> None:
        server = self._get_focused_server()
        if server:
            self.run_worker(self._probe_single_server_worker(server))

    def action_refresh_fleet(self) -> None:
        self.run_worker(self._probe_fleet_worker(fetch_metrics=True))

    def _scheduled_fleet_refresh(self) -> None:
        self.run_worker(self._probe_fleet_worker(fetch_metrics=True))

    async def _probe_single_server_worker(self, server: Server) -> None:
        updated = await SSHService.probe_server_health(
            server, vault=self._vault, fetch_metrics=True
        )
        self._repository.update_telemetry(
            server_id=updated.id,
            status=updated.status,
            latency_ms=updated.latency_ms,
            metrics=updated.metrics,
        )
        self.reload_servers_from_storage()

    async def _probe_fleet_worker(self, fetch_metrics: bool = True) -> None:
        if self._polling_active or not self._all_servers:
            return

        self._polling_active = True
        semaphore = asyncio.Semaphore(12)

        async def _probe_bounded(srv: Server) -> None:
            async with semaphore:
                try:
                    updated = await SSHService.probe_server_health(
                        srv,
                        vault=self._vault,
                        fetch_metrics=fetch_metrics,
                    )
                    self._repository.update_telemetry(
                        server_id=updated.id,
                        status=updated.status,
                        latency_ms=updated.latency_ms,
                        metrics=updated.metrics,
                    )
                except Exception:
                    pass

        try:
            tasks = [_probe_bounded(server) for server in self._all_servers]
            await asyncio.gather(*tasks, return_exceptions=True)
            self.reload_servers_from_storage()
        finally:
            self._polling_active = False
