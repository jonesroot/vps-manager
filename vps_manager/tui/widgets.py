"""
vps_manager.tui.widgets
~~~~~~~~~~~~~~~~~~~~~~~

Modular, reactive Textual widgets for system metrics visualization,
telemetry badges, dynamic resource gauges, and server data tables.

:copyright: (c) 2025 by Elite Systems Architecture.
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, DataTable, Static

from vps_manager.models import (
    Server,
    ServerStatus,
)


# ============================================================================
# STATUS BADGE & TELEMETRY PILL
# ============================================================================


class StatusBadge(Widget):
    """Reactive badge displaying node status and network latency."""

    DEFAULT_CSS = """
    StatusBadge {
        width: auto;
        height: 1;
        padding: 0 1;
    }
    """

    status: reactive[ServerStatus] = reactive(ServerStatus.UNCHECKED)
    latency_ms: reactive[float | None] = reactive(None)

    def __init__(
        self,
        status: ServerStatus = ServerStatus.UNCHECKED,
        latency_ms: float | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.status = status
        self.latency_ms = latency_ms

    def render(self) -> Text:
        text = Text()

        match self.status:
            case ServerStatus.ONLINE:
                text.append("● ONLINE", style="bold green")
            case ServerStatus.OFFLINE:
                text.append("○ OFFLINE", style="bold red")
            case ServerStatus.AUTH_FAILED:
                text.append("✕ AUTH FAIL", style="bold magenta")
            case ServerStatus.TIMEOUT:
                text.append("⏱ TIMEOUT", style="bold yellow")
            case ServerStatus.ERROR:
                text.append("▲ ERROR", style="bold red")
            case ServerStatus.UNCHECKED:
                text.append("◌ UNCHECKED", style="dim white")

        if self.status == ServerStatus.ONLINE and self.latency_ms is not None:
            lat = self.latency_ms
            lat_style = "green" if lat < 100.0 else ("yellow" if lat < 250.0 else "bold red")
            text.append(f" ({lat:.1f}ms)", style=lat_style)

        return text


# ============================================================================
# DYNAMIC RESOURCE GAUGE BAR
# ============================================================================


class ResourceBar(Widget):
    """Dynamic progress bar with percentage-based threshold color shifts."""

    DEFAULT_CSS = """
    ResourceBar {
        width: 100%;
        height: 1;
        layout: horizontal;
    }
    .gauge-label {
        width: 6;
        text-style: bold;
        color: $text-muted;
    }
    .gauge-bar {
        width: 1fr;
    }
    .gauge-value {
        width: 22;
        text-align: right;
        color: $text;
    }
    """

    percentage: reactive[float] = reactive(0.0)
    detail_text: reactive[str] = reactive("")

    def __init__(
        self,
        label: str,
        percentage: float = 0.0,
        detail_text: str = "",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._label: Final[str] = label
        self.percentage = max(0.0, min(100.0, percentage))
        self.detail_text = detail_text

    def compose(self) -> ComposeResult:
        yield Static(f"{self._label}:", classes="gauge-label")
        yield Static("", id=f"{self._label.lower()}-bar-display", classes="gauge-bar")
        yield Static(self.detail_text, id=f"{self._label.lower()}-val-display", classes="gauge-value")

    def on_mount(self) -> None:
        """Render bar visualization immediately upon mounting."""
        self._update_display()

    def watch_percentage(self, new_val: float) -> None:
        if self.is_mounted:
            self._update_display()

    def watch_detail_text(self, new_val: str) -> None:
        if self.is_mounted:
            try:
                val_widget = self.query_one(f"#{self._label.lower()}-val-display", Static)
                val_widget.update(new_val)
            except Exception:
                pass

    def _update_display(self) -> None:
        try:
            bar_widget = self.query_one(f"#{self._label.lower()}-bar-display", Static)
            val_widget = self.query_one(f"#{self._label.lower()}-val-display", Static)
        except Exception:
            return

        pct = max(0.0, min(100.0, self.percentage))
        total_slots = 16

        filled_slots = int((pct / 100.0) * total_slots)
        empty_slots = total_slots - filled_slots

        color = "green" if pct < 70.0 else ("yellow" if pct < 85.0 else "bold red")

        bar_text = Text()
        bar_text.append("█" * filled_slots, style=color)
        bar_text.append("░" * empty_slots, style="dim white")
        bar_text.append(f" {pct:.1f}%", style=color)

        bar_widget.update(bar_text)
        val_widget.update(self.detail_text)


# ============================================================================
# SERVER TELEMETRY DETAIL CARD
# ============================================================================


class ServerTelemetryCard(Widget):
    """Detailed live telemetry dashboard with integrated connect trigger."""

    DEFAULT_CSS = """
    ServerTelemetryCard {
        width: 100%;
        height: 100%;
        background: $surface;
        border: round $primary;
        padding: 1 2;
    }
    .info-header {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
        border-bottom: solid $primary-muted;
    }
    .meta-content {
        margin-top: 1;
        height: auto;
        color: $text;
    }
    .metric-section {
        margin-top: 1;
        border-top: solid $primary-muted;
        padding-top: 1;
    }
    #btn-card-connect {
        width: 100%;
        margin-top: 1;
        text-style: bold;
        height: 3;
    }
    """

    server: reactive[Server | None] = reactive(None)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("SERVER INSPECTOR", classes="info-header", id="inspector-title")
            yield Static("Select a server from the table to inspect.", id="inspector-meta", classes="meta-content")
            with Vertical(id="gauges-container", classes="metric-section"):
                yield ResourceBar(label="CPU", id="card-cpu-bar")
                yield ResourceBar(label="RAM", id="card-ram-bar")
                yield ResourceBar(label="DSK", id="card-dsk-bar")
            yield Button("▶ Connect to Shell [Enter]", variant="success", id="btn-card-connect")

    def on_mount(self) -> None:
        """Render server details on initial mount."""
        self._render_details(self.server)

    def watch_server(self, srv: Server | None) -> None:
        if self.is_mounted:
            self._render_details(srv)

    def _render_details(self, srv: Server | None) -> None:
        try:
            title_widget = self.query_one("#inspector-title", Static)
            meta_widget = self.query_one("#inspector-meta", Static)
            cpu_bar = self.query_one("#card-cpu-bar", ResourceBar)
            ram_bar = self.query_one("#card-ram-bar", ResourceBar)
            dsk_bar = self.query_one("#card-dsk-bar", ResourceBar)
            btn_connect = self.query_one("#btn-card-connect", Button)
        except Exception:
            return

        if srv is None:
            title_widget.update("SERVER INSPECTOR")
            meta_widget.update(
                Text.from_markup(
                    "[dim]No active node selected.\n\n"
                    "• Use [bold cyan]↑ / ↓[/] keys to navigate servers\n"
                    "• Press [bold cyan]Enter[/] to open interactive shell\n"
                    "• Press [bold cyan]a[/] to add your first node[/dim]"
                )
            )
            cpu_bar.percentage = 0.0
            cpu_bar.detail_text = "Idle"
            ram_bar.percentage = 0.0
            ram_bar.detail_text = "Idle"
            dsk_bar.percentage = 0.0
            dsk_bar.detail_text = "Idle"
            btn_connect.disabled = True
            return

        btn_connect.disabled = False
        title_widget.update(f"NODE: {srv.alias.upper()}")

        meta = Text()
        meta.append("Endpoint: ", style="bold dim")
        meta.append(f"{srv.user}@{srv.host}:{srv.port}\n", style="bold white")
        meta.append("Status  : ", style="bold dim")
        meta.append(
            f"{srv.status.value.upper()} ",
            style="bold green" if srv.status == ServerStatus.ONLINE else "bold red",
        )
        if srv.latency_ms is not None:
            meta.append(f"({srv.latency_ms:.1f} ms) ", style="green")
        meta.append(f"• Group: {srv.group} • Auth: {srv.auth_type.value}\n")

        if srv.metrics:
            m = srv.metrics
            meta.append("System  : ", style="bold dim")
            meta.append(f"{m.os_name} ({m.kernel})\n")
            meta.append("Uptime  : ", style="bold dim")
            meta.append(f"{m.uptime_human} • Load: {m.formatted_load}")

            meta_widget.update(meta)

            cpu_bar.percentage = m.cpu_usage_pct
            cpu_bar.detail_text = f"{m.cpu_count} Cores ({m.cpu_usage_pct:.1f}%)"

            ram_bar.percentage = m.mem_usage_pct
            ram_bar.detail_text = f"{m.mem_used_human} / {m.mem_total_human}"

            dsk_bar.percentage = m.disk_usage_pct
            dsk_bar.detail_text = f"{m.disk_used_human} / {m.disk_total_human}"
        else:
            meta.append("\n[Telemetry data not yet collected. Press 'r' to probe.]")
            meta_widget.update(meta)
            cpu_bar.percentage = 0.0
            cpu_bar.detail_text = "N/A"
            ram_bar.percentage = 0.0
            ram_bar.detail_text = "N/A"
            dsk_bar.percentage = 0.0
            dsk_bar.detail_text = "N/A"


# ============================================================================
# FLEET SUMMARY BANNER
# ============================================================================


class FleetSummaryBar(Widget):
    """Header widget presenting aggregated statistics across all servers."""

    DEFAULT_CSS = """
    FleetSummaryBar {
        width: 100%;
        height: 1;
        background: $primary-darken-3;
        color: $text;
        padding: 0 1;
    }
    """

    total_count: reactive[int] = reactive(0)
    online_count: reactive[int] = reactive(0)
    offline_count: reactive[int] = reactive(0)
    avg_latency: reactive[float] = reactive(0.0)

    def render(self) -> Text:
        t = Text()
        t.append("FLEET OVERVIEW: ", style="bold white")
        t.append(f"Total: {self.total_count} ", style="bold cyan")
        t.append("│ ", style="dim white")
        t.append(f"Online: {self.online_count} ", style="bold green")
        t.append("│ ", style="dim white")
        t.append(
            f"Offline: {self.offline_count} ",
            style="bold red" if self.offline_count > 0 else "dim white",
        )
        t.append("│ ", style="dim white")
        t.append(
            f"Avg Ping: {self.avg_latency:.1f}ms",
            style="yellow" if self.avg_latency > 0 else "dim white",
        )
        return t

    def update_from_servers(self, servers: Sequence[Server]) -> None:
        total = len(servers)
        online = sum(1 for s in servers if s.status == ServerStatus.ONLINE)
        offline = sum(
            1
            for s in servers
            if s.status
            in (ServerStatus.OFFLINE, ServerStatus.TIMEOUT, ServerStatus.ERROR)
        )

        latencies = [
            s.latency_ms
            for s in servers
            if s.latency_ms is not None and s.status == ServerStatus.ONLINE
        ]
        avg_lat = (sum(latencies) / len(latencies)) if latencies else 0.0

        self.total_count = total
        self.online_count = online
        self.offline_count = offline
        self.avg_latency = avg_lat


# ============================================================================
# HIGH-PERFORMANCE SERVER DATA TABLE
# ============================================================================


class ServerDataTable(DataTable[str]):
    """Specialized DataTable with optimized column geometry and batch selection."""

    DEFAULT_CSS = """
    ServerDataTable {
        height: 1fr;
        border: round $primary-muted;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes, cursor_type="row")
        self._selected_ids: set[str] = set()
        self._ordered_ids: list[str] = []

    def on_mount(self) -> None:
        self.add_column("SEL", width=4, key="col_sel")
        self.add_column("STATUS", width=14, key="col_status")
        self.add_column("ALIAS", width=14, key="col_alias")
        self.add_column("ENDPOINT", width=22, key="col_endpoint")
        self.add_column("GROUP", width=12, key="col_group")
        self.add_column("CPU", width=7, key="col_cpu")
        self.add_column("RAM", width=8, key="col_ram")
        self.add_column("DISK", width=7, key="col_disk")
        self.add_column("UPTIME", width=12, key="col_uptime")

    def toggle_selection(self, server_id: str) -> None:
        if server_id in self._selected_ids:
            self._selected_ids.remove(server_id)
        else:
            self._selected_ids.add(server_id)

        if server_id in self._ordered_ids:
            is_sel = server_id in self._selected_ids
            sel_text = Text("[X]", style="bold green") if is_sel else Text("[ ]", style="dim white")
            try:
                self.update_cell(server_id, "col_sel", sel_text)
            except Exception:
                pass

    def get_selected_server_ids(self) -> set[str]:
        return set(self._selected_ids)

    def populate_servers(self, servers: Sequence[Server]) -> None:
        """Populate or update table rows.

        Uses in-place cell updating when row identities and order match to eliminate
        visual redraw flicker and preserve cursor position during telemetry polling.
        """
        new_ids = [s.id for s in servers]

        # In-place update if row keys and order are identical
        if new_ids == self._ordered_ids:
            for s in servers:
                self._update_server_row(s)
            return

        # Structural change: remember focused server ID to restore cursor
        saved_id: str | None = None
        if self.row_count > 0 and self.cursor_row >= 0:
            try:
                row_key, _ = self.coordinate_to_cell_key(self.cursor_coordinate)
                saved_id = row_key.value
            except Exception:
                pass

        self.clear(columns=False)
        self._ordered_ids.clear()

        restore_idx: int | None = None
        for idx, s in enumerate(servers):
            self._insert_server_row(s)
            self._ordered_ids.append(s.id)
            if saved_id is not None and s.id == saved_id:
                restore_idx = idx

        if restore_idx is not None and self.row_count > 0:
            self.move_cursor(row=restore_idx)

    def _render_row_cells(self, s: Server) -> tuple[Text, ...]:
        is_sel = s.id in self._selected_ids
        sel_text = Text("[X]", style="bold green") if is_sel else Text("[ ]", style="dim white")

        status_text = Text()
        match s.status:
            case ServerStatus.ONLINE:
                status_text.append("● ON", style="bold green")
                if s.latency_ms is not None:
                    status_text.append(f" {s.latency_ms:.0f}ms", style="green")
            case ServerStatus.OFFLINE:
                status_text.append("○ OFF", style="bold red")
            case ServerStatus.TIMEOUT:
                status_text.append("⏱ TIME", style="bold yellow")
            case ServerStatus.AUTH_FAILED:
                status_text.append("✕ AUTH", style="bold magenta")
            case ServerStatus.ERROR:
                status_text.append("▲ ERR", style="bold red")
            case ServerStatus.UNCHECKED:
                status_text.append("◌ UNCHK", style="dim white")

        alias_text = Text(s.alias, style="bold cyan")
        endpoint_text = Text(f"{s.user}@{s.host}:{s.port}", style="white")
        group_text = Text(s.group, style="blue")

        if s.metrics:
            m = s.metrics
            cpu_style = "green" if m.cpu_usage_pct < 70 else ("yellow" if m.cpu_usage_pct < 85 else "bold red")
            cpu_text = Text(f"{m.cpu_usage_pct:.0f}%", style=cpu_style)

            ram_style = "green" if m.mem_usage_pct < 70 else ("yellow" if m.mem_usage_pct < 85 else "bold red")
            ram_text = Text(f"{m.mem_usage_pct:.0f}%", style=ram_style)

            dsk_style = "green" if m.disk_usage_pct < 70 else ("yellow" if m.disk_usage_pct < 85 else "bold red")
            dsk_text = Text(f"{m.disk_usage_pct:.0f}%", style=dsk_style)

            uptime_text = Text(m.uptime_human, style="dim white")
        else:
            cpu_text = Text("-", style="dim")
            ram_text = Text("-", style="dim")
            dsk_text = Text("-", style="dim")
            uptime_text = Text("-", style="dim")

        return (
            sel_text,
            status_text,
            alias_text,
            endpoint_text,
            group_text,
            cpu_text,
            ram_text,
            dsk_text,
            uptime_text,
        )

    def _insert_server_row(self, s: Server) -> None:
        cells = self._render_row_cells(s)
        self.add_row(*cells, key=s.id)

    def _update_server_row(self, s: Server) -> None:
        cells = self._render_row_cells(s)
        col_keys = (
            "col_sel",
            "col_status",
            "col_alias",
            "col_endpoint",
            "col_group",
            "col_cpu",
            "col_ram",
            "col_disk",
            "col_uptime",
        )
        for col_key, cell_value in zip(col_keys, cells, strict=True):
            try:
                self.update_cell(s.id, col_key, cell_value)
            except Exception:
                pass
