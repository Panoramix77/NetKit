"""
Módulo de interfaz TUI (Terminal User Interface).

Implementa el dashboard de NetKit usando la librería Textual.
Separa radicalmente la presentación de la lógica de red (core.red).
"""
import asyncio
import re
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Static, Button, Input, RichLog, ContentSwitcher, Select
from textual import work
from textual.reactive import reactive

from core import red


# ---------------------------------------------------------------------------
# Colorización de la salida de ping
# ---------------------------------------------------------------------------

def _colorize(line: str) -> str:
    """
    Aplica marcado Rich a una línea de salida de ping.

    Args:
        line: Línea de texto plano procedente del ping.

    Returns:
        Cadena con marcas Rich para coloreado en RichLog.
        Cadena vacía si la línea está vacía.
    """
    s = line.strip()
    lo = s.lower()

    if not s:
        return ""

    # ── Errores críticos ───────────────────────────────────────────────────
    if any(k in lo for k in (
        "error", "unknown host", "unreachable",
        "cannot resolve", "bad address", "no route",
    )):
        return f"[bold red]✗  {s}[/]"

    # ── Timeout ────────────────────────────────────────────────────────────
    if "timeout" in lo or "request timed out" in lo:
        return f"[red]⏱  {s}[/]"

    # ── Respuesta exitosa (Linux: "bytes from", Windows: "Reply from") ─────
    if re.search(r"bytes from|reply from", lo):
        return f"[bright_green]●  {s}[/]"

    # ── Cabecera de estadísticas ───────────────────────────────────────────
    if s.startswith("---") or "ping statistics" in lo:
        return f"[bold yellow]{s}[/]"

    # ── Línea de pérdida de paquetes ───────────────────────────────────────
    if re.search(r"transmitted|packets:|packet loss", lo):
        loss_match = re.search(r"(\d+)%\s*(?:packet\s*)?loss", lo)
        if loss_match:
            loss = int(loss_match.group(1))
            color = (
                "bold green" if loss == 0
                else "bold yellow" if loss < 50
                else "bold red"
            )
            return f"[{color}]{s}[/]"
        return f"[yellow]{s}[/]"

    # ── Estadísticas RTT ───────────────────────────────────────────────────
    if re.search(r"\brtt\b|round.trip|min.*avg.*max|minimum.*maximum|average", lo):
        return f"[bold cyan]{s}[/]"

    # ── Primera línea: cabecera PING / Pinging ─────────────────────────────
    if lo.startswith("ping") or lo.startswith("pinging"):
        return f"[bold blue]{s}[/]"

    # ── Resto de líneas ────────────────────────────────────────────────────
    return f"[dim]{s}[/]"


def _colorize_trace(line: str) -> str:
    """
    Aplica marcado Rich a una línea de salida de traceroute.
    """
    s = line.strip()
    lo = s.lower()

    if not s:
        return ""

    # Errores
    if any(k in lo for k in ("unreachable", "failed", "error", "perdido")):
        return f"[bold red]✗  {s}[/]"

    # Tiempos de espera / asteriscos
    if "*" in s:
        return f"[yellow]⏱  {s}[/]"

    # Cabeceras
    if any(k in lo for k in ("traceroute to", "trazando la ruta", "tracepath to")):
        return f"[bold blue]{s}[/]"

    # Saltos normales (líneas que empiezan por números, e.g. " 1 ", "1:")
    if re.match(r'^\s*\d+[:\s]', s) or re.match(r'^\d+\b', s):
        # Colorear IP (IPv4)
        line_colored = re.sub(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', r'[green]\1[/]', s)
        # Colorear tiempos (e.g., "1.23 ms" o "5 ms" o "1 ms")
        line_colored = re.sub(r'(\d+(?:\.\d+)?\s*ms)', r'[cyan]\1[/]', line_colored)
        return f"[bold white]{line_colored}[/]"

    return f"[dim]{s}[/]"


def copy_to_system_clipboard(text: str) -> bool:
    """
    Intenta copiar texto al portapapeles del sistema usando herramientas nativas de Linux
    (wl-copy para Wayland, xclip o xsel para X11). Retorna True si tiene éxito.
    """
    import subprocess
    import platform

    system = platform.system().lower()
    if system == "linux":
        # 1. Intentar wl-copy (Wayland, común en Arch moderno)
        try:
            process = subprocess.Popen(['wl-copy'], stdin=subprocess.PIPE, text=True)
            process.communicate(input=text)
            if process.returncode == 0:
                return True
        except FileNotFoundError:
            pass

        # 2. Intentar xclip (X11)
        try:
            process = subprocess.Popen(['xclip', '-selection', 'clipboard'], stdin=subprocess.PIPE, text=True)
            process.communicate(input=text)
            if process.returncode == 0:
                return True
        except FileNotFoundError:
            pass

        # 3. Intentar xsel (X11)
        try:
            process = subprocess.Popen(['xsel', '--clipboard', '--input'], stdin=subprocess.PIPE, text=True)
            process.communicate(input=text)
            if process.returncode == 0:
                return True
        except FileNotFoundError:
            pass

    return False


# ---------------------------------------------------------------------------
# Cabecera Personalizada
# ---------------------------------------------------------------------------

class NetKitHeader(Horizontal):
    """Cabecera personalizada con título, info de red y reloj."""

    def compose(self) -> ComposeResult:
        yield Static("NetKit - Diagnóstico y comprobación de red", id="header-title")
        yield Static("🔌 Detectando red...", id="header-info")
        with Vertical(id="header-right"):
            yield Static("", id="header-clock")
            yield Button("Salir", id="btn-quit", variant="error")

    def on_mount(self) -> None:
        self.update_clock()
        self.update_network_info()
        self.set_interval(1.0, self.update_clock)
        self.set_interval(10.0, self.update_network_info)

    def update_clock(self) -> None:
        self.query_one("#header-clock", Static).update(datetime.now().strftime("%H:%M:%S"))

    def update_network_info(self) -> None:
        try:
            iface, ip = red.get_active_interface_and_ip()
            self.query_one("#header-info", Static).update(f"🔌 {iface}: {ip}  ")
        except Exception:
            self.query_one("#header-info", Static).update("🔌 Sin conexión  ")


# ---------------------------------------------------------------------------
# Aplicación principal
# ---------------------------------------------------------------------------

class NetKitApp(App):
    """Dashboard TUI de NetKit."""

    TITLE = "NetKit - Diagnóstico y comprobación de red"
    SUB_TITLE = ""

    BINDINGS = [
        ("q",       "quit",          "Salir"),
        ("ctrl+l",  "clear_log",     "Limpiar log"),
    ]

    # Reactivos de estado
    is_running:       reactive[bool] = reactive(False)
    is_running_trace: reactive[bool] = reactive(False)
    is_running_lan:   reactive[bool] = reactive(False)
    is_running_ports: reactive[bool] = reactive(False)

    # ── CSS completo (dark por defecto + overrides light) ──────────────────
    CSS = """
    /* ═══════════════════════════════════════════════════════
       DARK THEME  (por defecto)
    ═══════════════════════════════════════════════════════ */

    Screen {
        background: #0d1117;
    }

    NetKitHeader {
        background: #161b22;
        color: #58a6ff;
        text-style: bold;
        height: 2;
    }

    #header-title {
        width: 1fr;
        padding-left: 1;
        content-align: left middle;
    }

    #header-info {
        width: auto;
        color: #8b949e;
        content-align: right middle;
        text-style: none;
    }

    #header-right {
        width: 10;
        align: right top;
        padding-right: 1;
    }

    #header-clock {
        width: 100%;
        color: #58a6ff;
        content-align: center middle;
    }
    
    #btn-quit {
        width: 100%;
        height: 1;
        min-width: 8;
        border: none;
    }

    Footer {
        background: #161b22;
        color: #6e7681;
    }

    #app-body {
        height: 1fr;
    }

    /* ── Sidebar ── */
    #sidebar {
        width: 24;
        background: #0d1117;
        border-right: solid #21262d;
        padding: 1 0;
    }

    #sb-title {
        color: #6e7681;
        text-style: bold;
        padding: 0 2;
        height: 2;
        content-align: left middle;
    }

    .tool-btn {
        width: 100%;
        height: 3;
        background: transparent;
        border: none;
        color: #8b949e;
        text-align: left;
        padding: 0 2;
        content-align: left middle;
    }

    .tool-btn:hover {
        background: #21262d;
        color: #e6edf3;
    }

    .tool-btn.-active {
        background: #1f6feb22;
        color: #58a6ff;
        border-left: solid #1f6feb;
        text-style: bold;
    }

    .tool-btn.-active:hover {
        background: #1f6feb33;
    }



    /* ── Área de contenido ── */
    #content {
        width: 1fr;
        padding: 2 3;
        background: #0d1117;
    }

    .tool-title {
        color: #58a6ff;
        text-style: bold;
        height: 1;
    }

    .tool-desc {
        color: #6e7681;
        height: 1;
        margin-bottom: 2;
    }

    #btn-refresh-ifaces {
        margin-bottom: 2;
        width: 22;
        margin-right: 1;
    }

    #interfaces-btn-row {
        height: 3;
        margin-bottom: 2;
    }

    #input-row, #input-row-trace, .input-row-class {
        height: 3;
        margin-bottom: 2;
    }

    #ping-host, #trace-host, #lan-subnet, #ports-host {
        width: 1fr;
        margin-right: 1;
    }

    #ports-mode { width: 22; margin-right: 1; }
    #ports-custom { width: 20; margin-right: 1; }
    #ports-protocol { width: 12; margin-right: 1; }

    /* Fake selector to keep old format string working if needed */
    .dummy-placeholder {
        width: 1fr;
        margin-right: 1;
    }

    #lbl-calc-ip, #lbl-calc-mask1, #lbl-calc-mask2 {
        width: auto;
        content-align: left middle;
        margin-right: 1;
        margin-left: 1;
        color: #6e7681;
    }

    #calc-host {
        width: 22;
        margin-right: 1;
    }

    #calc-mask1, #calc-mask2 {
        width: 16;
        margin-right: 1;
    }

    #lbl-count {
        width: 12;
        content-align: left middle;
        color: #6e7681;
    }

    #ping-count {
        width: 7;
        margin-right: 1;
    }

    #run-btn, #run-trace-btn, #run-lan-btn, #run-calc-btn {
        width: 18;
        min-width: 18;
    }

    .output-log {
        height: 1fr;
        background: #161b22;
        border: solid #30363d;
        padding: 1 2;
    }

    #app-bottom {
        dock: bottom;
        height: auto;
    }

    #footer-msg {
        content-align: center middle;
        height: 1;
        background: #161b22;
        color: #8b949e;
        text-style: italic;
    }
    """

    # ── Composición del layout ─────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield NetKitHeader()

        with Horizontal(id="app-body"):
            # ── Sidebar ─────────────────────────────────────────────────────
            with Vertical(id="sidebar"):
                yield Static("  HERRAMIENTAS", id="sb-title")
                yield Button("📋  Interfaces", id="btn-interfaces", classes="tool-btn -active")
                yield Button("🧮  Calculadora", id="btn-calc", classes="tool-btn")
                yield Button("🌐  Ping", id="btn-ping", classes="tool-btn")
                yield Button("🔍  Traceroute", id="btn-traceroute", classes="tool-btn")
                yield Button("📡  Escáner LAN", id="btn-lan", classes="tool-btn")
                yield Button("🛡️  Escáner Puertos", id="btn-ports", classes="tool-btn")

            # ── Contenido principal ──────────────────────────────────────────
            with Vertical(id="content"):
                with ContentSwitcher(initial="view-interfaces"):
                    # ── Vista de Interfaces ──
                    with Vertical(id="view-interfaces"):
                        yield Static("📋  INFO DE INTERFACES", id="tool-name-ifaces", classes="tool-title")
                        yield Static(
                            "Detalle completo de todas las interfaces de red físicas y virtuales del sistema.",
                            id="tool-desc-ifaces",
                            classes="tool-desc"
                        )
                        with Horizontal(id="interfaces-btn-row"):
                            yield Button("🔄  Actualizar Info", id="btn-refresh-ifaces", variant="primary")
                        yield RichLog(id="ifaces-output", classes="output-log", markup=True, highlight=False, wrap=True)

                    # ── Vista de Calculadora IP ──
                    with Vertical(id="view-calc"):
                        yield Static("🧮  CALCULADORA DE SUBREDES IP", id="tool-name-calc", classes="tool-title")
                        yield Static(
                            "Introduce una IP con su máscara (CIDR o formato decimal) para calcular los detalles de la red.",
                            id="tool-desc-calc",
                            classes="tool-desc"
                        )
                        with Horizontal(id="input-row-calc", classes="input-row-class"):
                            yield Static("IP:", id="lbl-calc-ip")
                            yield Input(placeholder="e.g. 192.168.1.53", id="calc-host")
                            yield Static("Netmask:", id="lbl-calc-mask1")
                            yield Input(placeholder="e.g. 24", id="calc-mask1")
                            yield Static("Supernet/Subnet (opt):", id="lbl-calc-mask2")
                            yield Input(placeholder="e.g. 26", id="calc-mask2")
                            yield Button("▶  Calcular", id="run-calc-btn", variant="success")

                        yield RichLog(id="calc-output", classes="output-log", markup=True, highlight=False, wrap=True)

                    # ── Vista de Ping ──
                    with Vertical(id="view-ping"):
                        yield Static("🌐  PING", id="tool-name-ping", classes="tool-title")
                        yield Static(
                            "Comprueba conectividad y latencia con un host o dirección IP.",
                            id="tool-desc-ping",
                            classes="tool-desc"
                        )
                        with Horizontal(id="input-row", classes="input-row-class"):
                            yield Input(
                                placeholder="Host o IP  (ej: google.com · 8.8.8.8 · 1.1.1.1)",
                                id="ping-host",
                            )
                            yield Static("Paquetes:", id="lbl-count")
                            yield Input(value="4", id="ping-count", max_length=3)
                            yield Button("▶  Iniciar", id="run-btn", variant="success")

                        yield RichLog(id="ping-output", classes="output-log", markup=True, highlight=False, wrap=True)

                    # ── Vista de Traceroute ──
                    with Vertical(id="view-traceroute"):
                        yield Static("🔍  TRACEROUTE", id="tool-name-trace", classes="tool-title")
                        yield Static(
                            "Realiza un seguimiento de la ruta que siguen los paquetes de red hasta un host.",
                            id="tool-desc-trace",
                            classes="tool-desc"
                        )
                        with Horizontal(id="input-row-trace", classes="input-row-class"):
                            yield Input(
                                placeholder="Host o IP  (ej: google.com · 8.8.8.8)",
                                id="trace-host",
                            )
                            yield Button("▶  Iniciar", id="run-trace-btn", variant="success")

                        yield RichLog(id="trace-output", classes="output-log", markup=True, highlight=False, wrap=True)

                    # ── Vista de Escáner LAN ──
                    with Vertical(id="view-lan"):
                        yield Static("📡  ESCÁNER DE RED LOCAL (LAN)", id="tool-name-lan", classes="tool-title")
                        yield Static(
                            "Busca dispositivos activos en tu subred local enviando pings rápidos en paralelo.",
                            id="tool-desc-lan",
                            classes="tool-desc"
                        )
                        with Horizontal(id="input-row-lan", classes="input-row-class"):
                            yield Input(
                                placeholder="Subred (ej: 192.168.1.0/24)",
                                id="lan-subnet",
                            )
                            yield Button("▶  Escanear", id="run-lan-btn", variant="success")

                        yield RichLog(id="lan-output", classes="output-log", markup=True, highlight=False, wrap=True)

                    # ── Vista de Escáner de Puertos ──
                    with Vertical(id="view-ports"):
                        yield Static("🛡️  ESCÁNER DE PUERTOS", id="tool-name-ports", classes="tool-title")
                        yield Static(
                            "Escanea puertos TCP/UDP de un host para descubrir servicios y su estado.",
                            id="tool-desc-ports",
                            classes="tool-desc"
                        )
                        with Horizontal(id="input-row-ports", classes="input-row-class"):
                            yield Input(placeholder="Host/IP", id="ports-host")
                            yield Select(
                                options=[("Top 100", "top100"), ("Todos (1-65535)", "all"), ("Personalizado", "custom")],
                                value="top100",
                                id="ports-mode"
                            )
                            yield Input(placeholder="ej. 80,443", id="ports-custom", disabled=True)
                            yield Select(
                                options=[("TCP", "tcp"), ("UDP", "udp")],
                                value="tcp",
                                id="ports-protocol"
                            )
                            yield Button("▶  Escanear", id="run-ports-btn", variant="success")
                        yield RichLog(id="ports-output", classes="output-log", markup=True, highlight=False, wrap=True)

        with Vertical(id="app-bottom"):
            yield Static("Hecho por ❤️  por Panoramix", id="footer-msg")
            yield Footer()

    # ── Ciclo de vida ──────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Muestra el mensaje de bienvenida al arrancar y carga interfaces."""
        self._trace_worker = None
        self._lan_worker = None
        self._ports_worker = None
        self.ifaces_text_buffer = ""
        self.ping_text_buffer = ""
        self.trace_text_buffer = ""
        self.lan_text_buffer = ""
        self.calc_text_buffer = ""
        self._show_welcome()
        self._load_interfaces()
        self._initialize_lan_subnet()
        self._initialize_calc_ip()

    def _show_welcome(self) -> None:
        # Ping welcome
        try:
            log = self.query_one("#ping-output", RichLog)
            log.clear()
            log.write("[bold cyan]╔══════════════════════════════════════════╗[/]")
            log.write("[bold cyan]║   NetKit — Panel de Control de Red  v1   ║[/]")
            log.write("[bold cyan]╚══════════════════════════════════════════╝[/]")
            log.write("")
            log.write("[dim]Introduce un host o IP y pulsa [bold white]▶ Iniciar[/bold white].[/]")
            log.write("[dim]También puedes pulsar [bold white]Enter[/bold white] desde el campo de texto.[/]")
            log.write("")
            log.write("[dim]Ejemplos:[/]")
            log.write("[dim]  ● google.com      ● 8.8.8.8      ● 1.1.1.1[/]")
            log.write("")
        except Exception:
            pass

        # Traceroute welcome
        try:
            log_trace = self.query_one("#trace-output", RichLog)
            log_trace.clear()
            log_trace.write("[bold cyan]╔══════════════════════════════════════════╗[/]")
            log_trace.write("[bold cyan]║      NetKit — Trazador de Rutas TUI      ║[/]")
            log_trace.write("[bold cyan]╚══════════════════════════════════════════╝[/]")
            log_trace.write("")
            log_trace.write("[dim]Introduce un destino para analizar los saltos intermedios.[/]")
            log_trace.write("[dim]Pulsa [bold white]▶ Iniciar[/bold white] o [bold white]Enter[/bold white] para arrancar el trazado.[/]")
            log_trace.write("")
        except Exception:
            pass

        # LAN welcome
        try:
            log_lan = self.query_one("#lan-output", RichLog)
            log_lan.clear()
            log_lan.write("[bold cyan]╔══════════════════════════════════════════╗[/]")
            log_lan.write("[bold cyan]║     NetKit — Escáner de Red Local        ║[/]")
            log_lan.write("[bold cyan]╚══════════════════════════════════════════╝[/]")
            log_lan.write("")
            log_lan.write("[dim]Introduce una subred de red local (ej: 192.168.1.0/24).[/]")
            log_lan.write("[dim]El escáner enviará pings rápidos en paralelo para descubrir hosts.[/]")
            log_lan.write("[dim]Pulsa [bold white]▶ Escanear[/bold white] o [bold white]Enter[/bold white] para iniciar.[/]")
            log_lan.write("")
        except Exception:
            pass

        # Calculator welcome
        try:
            log_calc = self.query_one("#calc-output", RichLog)
            log_calc.clear()
            log_calc.write("[bold cyan]╔══════════════════════════════════════════╗[/]")
            log_calc.write("[bold cyan]║    NetKit — Calculadora de Subredes IP   ║[/]")
            log_calc.write("[bold cyan]╚══════════════════════════════════════════╝[/]")
            log_calc.write("")
            log_calc.write("[dim]Introduce una dirección IP seguida de su máscara.[/]")
            log_calc.write("[dim]Formatos válidos:[/]")
            log_calc.write("[dim]  ● CIDR: 192.168.1.53/24[/]")
            log_calc.write("[dim]  ● Decimal: 192.168.1.53 255.255.255.0[/]")
            log_calc.write("[dim]  ● Solo IP (asume /24): 10.0.0.1[/]")
            log_calc.write("")
            log_calc.write("[dim]Pulsa [bold white]▶ Calcular[/bold white] o [bold white]Enter[/bold white] para iniciar.[/]")
            log_calc.write("")
        except Exception:
            pass

        # Ports welcome
        try:
            log_ports = self.query_one("#ports-output", RichLog)
            log_ports.clear()
            log_ports.write("[bold cyan]╔══════════════════════════════════════════╗[/]")
            log_ports.write("[bold cyan]║      NetKit — Escáner de Puertos         ║[/]")
            log_ports.write("[bold cyan]╚══════════════════════════════════════════╝[/]")
            log_ports.write("")
            log_ports.write("[dim]Descubre los puertos y servicios de equipos remotos.[/]")
            log_ports.write("")
            log_ports.write("[bold white]Formatos de Búsqueda:[/]")
            log_ports.write("  [cyan]● IP o Dominio:[/cyan] [dim]192.168.1.1[/dim] o [dim]google.com[/dim]")
            log_ports.write("  [cyan]● Red o Rango:[/cyan]  [dim]192.168.1.0/24[/dim] o [dim]192.168.1.1-20[/dim]")
            log_ports.write("  [cyan]● Abreviaturas:[/cyan] [dim]192.168.1.1, 5, 10[/dim] (escaneará la .1, .5 y .10)")
            log_ports.write("")
            log_ports.write("[bold white]Leyenda de Estados:[/]")
            log_ports.write("[bold green]  ● OPEN[/]          El puerto acepta conexiones.")
            log_ports.write("[bold yellow]  ● FILTERED[/]      Un firewall bloquea la respuesta.")
            log_ports.write("[bold red]  ● CLOSED[/]        Accesible pero sin servicio escuchando.")
            log_ports.write("[bold cyan]  ● OPEN|FILTERED[/] (UDP) Abierto o ignorado por firewall.")
            log_ports.write("")
            log_ports.write("[dim]Configura los parámetros y pulsa [bold white]▶ Escanear[/bold white].[/]")
            log_ports.write("")
        except Exception:
            pass

    # ── Reactividad ────────────────────────────────────────────────────────

    def watch_is_running(self, running: bool) -> None:
        """Sincroniza el botón Iniciar/Detener con el estado del ping."""
        try:
            btn = self.query_one("#run-btn", Button)
            if running:
                btn.label = "⏹  Detener"
                btn.variant = "error"
            else:
                btn.label = "▶  Iniciar"
                btn.variant = "success"
        except Exception:
            pass

    def watch_is_running_trace(self, running: bool) -> None:
        """Sincroniza el botón Iniciar/Detener con el estado del traceroute."""
        try:
            btn = self.query_one("#run-trace-btn", Button)
            if running:
                btn.label = "⏹  Detener"
                btn.variant = "error"
            else:
                btn.label = "▶  Iniciar"
                btn.variant = "success"
        except Exception:
            pass

    def watch_is_running_ports(self, running: bool) -> None:
        try:
            btn = self.query_one("#run-ports-btn", Button)
            if running:
                btn.label = "⏹  Detener"
                btn.variant = "error"
            else:
                btn.label = "▶  Escanear"
                btn.variant = "success"
        except Exception:
            pass

    def watch_is_running_lan(self, running: bool) -> None:
        """Sincroniza el botón Iniciar/Detener con el estado del escáner LAN."""
        try:
            btn = self.query_one("#run-lan-btn", Button)
            if running:
                btn.label = "⏹  Detener"
                btn.variant = "error"
            else:
                btn.label = "▶  Escanear"
                btn.variant = "success"
        except Exception:
            pass

    def _initialize_lan_subnet(self) -> None:
        try:
            subnets = red.detect_local_subnets()
            if subnets:
                self.query_one("#lan-subnet", Input).value = subnets[0]
            else:
                self.query_one("#lan-subnet", Input).value = "192.168.1.0/24"
        except Exception:
            try:
                self.query_one("#lan-subnet", Input).value = "192.168.1.0/24"
            except Exception:
                pass

    def _initialize_calc_ip(self) -> None:
        try:
            iface, ip = red.get_active_interface_and_ip()
            if ip and ip != "127.0.0.1":
                self.query_one("#calc-host", Input).value = ip
                subnets = red.detect_local_subnets()
                if subnets:
                    prefix = subnets[0].split("/")[-1]
                    self.query_one("#calc-mask1", Input).value = prefix
                else:
                    self.query_one("#calc-mask1", Input).value = "24"
            else:
                self.query_one("#calc-host", Input).value = "192.168.1.1"
                self.query_one("#calc-mask1", Input).value = "24"
            self.query_one("#calc-mask2", Input).value = ""
        except Exception:
            try:
                self.query_one("#calc-host", Input).value = "192.168.1.1"
                self.query_one("#calc-mask1", Input).value = "24"
                self.query_one("#calc-mask2", Input).value = ""
            except Exception:
                pass

    # ── Lógica de ejecución ────────────────────────────────────────────────

    def _execute(self) -> None:
        """Inicia o detiene el ping según el estado actual."""
        if self.is_running:
            self.workers.cancel_all()
            return

        host      = self.query_one("#ping-host",  Input).value.strip()
        count_raw = self.query_one("#ping-count",  Input).value.strip()

        if not host:
            self.query_one("#ping-output", RichLog).write(
                "[bold red]⚠  Por favor, introduce un host o dirección IP.[/]"
            )
            return

        try:
            count = max(1, min(50, int(count_raw)))
        except ValueError:
            count = 4

        self._run_ping(host, count)

    # ── Handlers de eventos ────────────────────────────────────────────────

    def _switch_view(self, view_id: str, active_button: Button) -> None:
        """Cambia la vista del ContentSwitcher y actualiza la clase -active de los botones."""
        self.query_one(ContentSwitcher).current = view_id
        for btn in self.query(".tool-btn"):
            btn.remove_class("-active")
        active_button.add_class("-active")

    @work(exclusive=True)
    async def _load_interfaces(self) -> None:
        """Carga la información de interfaces en segundo plano y la muestra."""
        from rich.table import Table
        log = self.query_one("#ifaces-output", RichLog)
        log.clear()
        log.write("[bold cyan]🔄 Buscando interfaces de red en el sistema...[/]")
        
        loop = asyncio.get_running_loop()
        try:
            ifaces = await loop.run_in_executor(None, red.get_interfaces_info)
        except Exception as exc:
            log.clear()
            log.write(f"[bold red]❌ Error al obtener interfaces: {exc}[/]")
            return

        log.clear()
        if not ifaces:
            log.write("[bold red]⚠ No se detectaron interfaces de red activas.[/]")
            return

        self.ifaces_text_buffer = ""
        
        table = Table(title="Interfaces de Red", show_header=True, header_style="bold cyan", expand=True)
        table.add_column("Estado", justify="center")
        table.add_column("Interfaz", style="bold white")
        table.add_column("MAC Address", style="yellow")
        table.add_column("IPv4", style="green")
        table.add_column("IPv6", style="magenta")

        for iface in ifaces:
            name = iface["name"]
            status = iface["status"]
            mac = iface["mac"]
            ipv4_list = iface["ipv4"]
            ipv6_list = iface["ipv6"]

            status_color = "bright_green" if status == "UP" else ("red" if status == "DOWN" else "yellow")
            status_icon = "🟢 UP" if status == "UP" else ("🔴 DOWN" if status == "DOWN" else "🟡 UNK")
            
            ipv4_str = "\n".join(ipv4_list) if ipv4_list else "[dim]Ninguna[/]"
            ipv6_str = "\n".join(ipv6_list) if ipv6_list else "[dim]Ninguna[/]"

            table.add_row(
                f"[{status_color}]{status_icon}[/]",
                name,
                mac,
                ipv4_str,
                ipv6_str
            )
            
            self.ifaces_text_buffer += f"{status} | {name} | {mac} | {', '.join(ipv4_list)} | {', '.join(ipv6_list)}\n"

        log.write(table)

    def _execute_trace(self) -> None:
        """Inicia o detiene el traceroute según el estado actual."""
        if self.is_running_trace:
            if self._trace_worker:
                self._trace_worker.cancel()
            return

        host = self.query_one("#trace-host", Input).value.strip()
        if not host:
            self.query_one("#trace-output", RichLog).write(
                "[bold red]⚠  Por favor, introduce un host o dirección IP de destino.[/]"
            )
            return

        self._trace_worker = self._run_trace(host)

    def _execute_lan(self) -> None:
        """Inicia o detiene el escaneo de red local según el estado actual."""
        if self.is_running_lan:
            if self._lan_worker:
                self._lan_worker.cancel()
            return

        subnet = self.query_one("#lan-subnet", Input).value.strip()
        if not subnet:
            self.query_one("#lan-output", RichLog).write(
                "[bold red]⚠  Por favor, introduce una subred de red local.[/]"
            )
            return

        self._lan_worker = self._run_lan(subnet)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "ports-mode":
            custom_input = self.query_one("#ports-custom", Input)
            if event.value == "custom":
                custom_input.disabled = False
                custom_input.focus()
            else:
                custom_input.disabled = True

    def _execute_ports(self) -> None:
        if self.is_running_ports:
            if self._ports_worker:
                self._ports_worker.cancel()
            return

        host_input = self.query_one("#ports-host", Input).value.strip()
        if not host_input:
            self.query_one("#ports-output", RichLog).write("[bold red]⚠  Introduce un host, IP, rango o subred.[/]")
            return

        ips = red.parse_target_ips(host_input)
        if not ips:
            self.query_one("#ports-output", RichLog).write("[bold red]⚠  Formato de destino inválido.[/]")
            return

        mode = self.query_one("#ports-mode", Select).value
        protocol = self.query_one("#ports-protocol", Select).value
        
        ports = []
        if mode == "top100":
            ports = red.get_top_ports()
        elif mode == "all":
            ports = list(range(1, 65536))
        else:
            custom_str = self.query_one("#ports-custom", Input).value.strip()
            for part in custom_str.split(","):
                part = part.strip()
                if not part: continue
                if "-" in part:
                    try:
                        start, end = map(int, part.split("-"))
                        ports.extend(range(start, end + 1))
                    except ValueError:
                        pass
                else:
                    try:
                        ports.append(int(part))
                    except ValueError:
                        pass
            if not ports:
                self.query_one("#ports-output", RichLog).write("[bold red]⚠  Formato de puertos inválido.[/]")
                return

        self._ports_worker = self._run_ports(ips, ports, protocol, host_input)

    def _execute_calc(self) -> None:
        """Realiza el cálculo de la subred y muestra los resultados exactamente al estilo ipcalc."""
        host = self.query_one("#calc-host", Input).value.strip()
        mask1 = self.query_one("#calc-mask1", Input).value.strip()
        mask2 = self.query_one("#calc-mask2", Input).value.strip()
        log = self.query_one("#calc-output", RichLog)
        
        if not host:
            log.clear()
            log.write("[bold red]⚠  Por favor, introduce una dirección IP.[/]")
            return
            
        res = red.calculate_subnet(host, mask1, mask2)
        log.clear()
        
        if not res["success"]:
            log.write(f"[bold red]❌ {res['error']}[/]")
            self.calc_text_buffer = f"Error: {res['error']}\n"
            return
            
        buf = ""
        
        def write_line(label: str, val: str, binary: str, comment: str = "", bin_color: str = "bright_black"):
            nonlocal buf
            lbl_pad = f"{label:<11}"
            val_pad = f"{val:<22}"
            
            rich_line = f"[bold white]{lbl_pad}[/][cyan]{val_pad}[/][{bin_color}]{binary}[/]"
            if comment:
                rich_line += f" [yellow]{comment}[/]"
                
            log.write(rich_line)
            buf += f"{lbl_pad}{val_pad}{binary}"
            if comment:
                buf += f" {comment}"
            buf += "\n"
            
        # Bloque principal
        write_line("Address:", res["ip"], res["binary_ip"], bin_color="cyan")
        write_line("Netmask:", f"{res['netmask']} = {res['prefix_len']}", res["binary_mask"], bin_color="red")
        write_line("Wildcard:", res["wildcard"], res["binary_wildcard"])
        
        log.write("=>")
        buf += "=>\n"
        
        write_line("Network:", f"{res['network']}/{res['prefix_len']}", res["binary_network"], res["network_comment"], bin_color="cyan")
        write_line("Broadcast:", res["broadcast"], res["binary_broadcast"])
        write_line("HostMin:", res["host_min"], res["binary_host_min"])
        write_line("HostMax:", res["host_max"], res["binary_host_max"])
        write_line("Hosts/Net:", res["hosts_count"], "", res["private_comment"])
        
        # Bloque opcional de Subnetting / Supernetting
        if "subnetting" in res:
            sub = res["subnetting"]
            log.write("")
            log.write("[bold magenta]Subnets[/]")
            log.write("")
            buf += "\nSubnets\n\n"
            
            write_line("Netmask:", f"{sub['netmask']} = {res['mask2_prefix_len']}", sub["binary_mask"], bin_color="red")
            write_line("Wildcard:", sub["wildcard"], sub["binary_wildcard"])
            log.write("")
            buf += "\n"
            
            for s in sub["subnets"]:
                write_line("Network:", f"{s['network']}/{res['mask2_prefix_len']}", s["binary_network"], f"( Class C )", bin_color="cyan")
                write_line("Broadcast:", s["broadcast"], s["binary_broadcast"])
                write_line("HostMin:", s["host_min"], s["binary_host_min"])
                write_line("HostMax:", s["host_max"], s["binary_host_max"])
                write_line("Hosts/Net:", s["hosts_count"], "", s["private_comment"])
                log.write("")
                buf += "\n"
                
            if sub["limit_reached"]:
                msg = f"... (se muestran las primeras {len(sub['subnets'])} subredes de {sub['num_subnets']} para evitar saturación) ..."
                log.write(f"[dim]{msg}[/]")
                buf += f"{msg}\n"
                
            lbl_sub = f"{'Subnets:':<11}"
            val_sub = f"{sub['num_subnets']}"
            log.write(f"[bold white]{lbl_sub}[/][cyan]{val_sub}[/]")
            buf += f"{lbl_sub}{val_sub}\n"
            
            lbl_hosts = f"{'Hosts:':<11}"
            val_hosts = f"{sub['total_hosts']}"
            log.write(f"[bold white]{lbl_hosts}[/][cyan]{val_hosts}[/]")
            buf += f"{lbl_hosts}{val_hosts}\n"
            
        elif "supernetting" in res:
            sup = res["supernetting"]
            log.write("")
            log.write("[bold magenta]Supernet[/]")
            log.write("")
            buf += "\nSupernet\n\n"
            
            write_line("Netmask:", f"{sup['netmask']} = {res['mask2_prefix_len']}", sup["binary_mask"], bin_color="red")
            write_line("Wildcard:", sup["wildcard"], sup["binary_wildcard"])
            log.write("=>")
            buf += "=>\n"
            
            write_line("Network:", f"{sup['network']}/{res['mask2_prefix_len']}", sup["binary_network"], res["network_comment"], bin_color="cyan")
            write_line("Broadcast:", sup["broadcast"], sup["binary_broadcast"])
            write_line("HostMin:", sup["host_min"], sup["binary_host_min"])
            write_line("HostMax:", sup["host_max"], sup["binary_host_max"])
            write_line("Hosts/Net:", sup["hosts_count"], "", sup["private_comment"])
            
        self.calc_text_buffer = buf

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "btn-quit":
                self.exit()
            case "btn-interfaces":
                self._switch_view("view-interfaces", event.button)
                self._load_interfaces()
            case "btn-ports":
                self._switch_view("view-ports", event.button)
            case "btn-lan":
                self._switch_view("view-lan", event.button)
            case "btn-calc":
                self._switch_view("view-calc", event.button)
            case "btn-traceroute":
                self._switch_view("view-traceroute", event.button)
            case "btn-ping":
                self._switch_view("view-ping", event.button)
            case "btn-refresh-ifaces":
                self._load_interfaces()
            case "run-btn":
                self._execute()
            case "run-trace-btn":
                self._execute_trace()
            case "run-ports-btn":
                self._execute_ports()
            case "run-lan-btn":
                self._execute_lan()
            case "run-calc-btn":
                self._execute_calc()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Permite lanzar comandos pulsando Enter desde cualquier campo."""
        if event.input.id in ("ping-host", "ping-count"):
            self._execute()
        elif event.input.id == "trace-host":
            self._execute_trace()
        elif event.input.id == "lan-subnet":
            self._execute_lan()
        elif event.input.id in ("calc-host", "calc-mask1", "calc-mask2"):
            self._execute_calc()

    # ── Acciones del teclado ───────────────────────────────────────────────

    def action_clear_log(self) -> None:
        """Limpia todos los logs y restaura las pantallas de bienvenida (Ctrl+L)."""
        self._show_welcome()

    # ── Workers asíncronos ──────────────────────────────────────────────────

    @work(exclusive=True)
    async def _run_ports(self, ips: list[str], ports: list[int], protocol: str, original_target: str) -> None:
        log = self.query_one("#ports-output", RichLog)
        self.is_running_ports = True

        log.clear()
        log.write(f"[bold white]⟶  Escaneando puertos ({protocol.upper()})[/] en [cyan]{original_target}[/]")
        log.write(f"[dim]Escaneando {len(ports)} puertos en {len(ips)} hosts ({len(ips)*len(ports)} pruebas)...[/]")

        try:
            results = []
            total_scans = len(ips) * len(ports)
            async for res in red.scan_ports_stream(ips, ports, protocol):
                results.append(res)
                if total_scans > 100 and len(results) % 500 == 0:
                    log.write(f"[dim]Progreso: {len(results)} / {total_scans}...[/]")

            def sort_key(r):
                import ipaddress
                st = r["state"]
                if st == "OPEN": st_val = 0
                elif st == "FILTERED": st_val = 1
                elif st == "OPEN|FILTERED": st_val = 2
                else: st_val = 3
                
                try:
                    ip_val = int(ipaddress.IPv4Address(r["ip"]))
                except Exception:
                    ip_val = 0
                    
                return (ip_val, st_val, r["port"])

            results.sort(key=sort_key)

            log.auto_scroll = False
            log.clear()
            log.write(f"[bold white]⟶  Resultados del escaneo ({protocol.upper()})[/] en [cyan]{original_target}[/]")
            
            from itertools import groupby
            arp_table = red._get_arp_table()
            
            for ip, group in groupby(results, key=lambda x: x["ip"]):
                group_list = list(group)
                
                hostname = await red._resolve_hostname(ip)
                mac = arp_table.get(ip, "N/A")
                vendor = red.get_mac_vendor(mac) if mac != "N/A" else ""
                
                host_str = ip
                if hostname:
                    host_str += f" [white]({hostname})[/]"
                if vendor:
                    host_str += f" [yellow][ {vendor} ][/]"
                
                log.write("")
                log.write(f"[bold cyan]Host: {host_str}[/]")
                log.write(f"[dim]{'─' * 60}[/]")
                log.write(f"[bold white]{'PUERTO':<10} {'ESTADO':<15} {'SERVICIO'}[/]")
                log.write(f"[dim]{'─' * 60}[/]")

                for res in group_list:
                    port = res["port"]
                    state = res["state"]
                    service = res["service"]

                    if state == "CLOSED" and len(ports) > 1000:
                        continue
                    
                    if state == "OPEN": color = "green"
                    elif state == "FILTERED": color = "yellow"
                    elif state == "CLOSED": color = "red"
                    else: color = "cyan"
                        
                    log.write(f"{port:<10} [{color}]{state:<15}[/] {service}")
                
            if len(ports) > 1000:
                log.write("")
                log.write("[dim]Nota: Los puertos cerrados se ocultan por limpieza visual.[/]")
                
        except asyncio.CancelledError:
            log.auto_scroll = False
            log.write("")
            log.write("[bold yellow]⏹  Escaneo detenido por el usuario.[/]")
        finally:
            log.write("")
            log.write(f"[dim]{'─' * 60}[/]")
            log.write("[dim]Finalizado.  (Ctrl+L para limpiar)[/]")
            
            log.scroll_home(animate=False)
            def restore_scroll():
                log.auto_scroll = True
            self.call_after_refresh(restore_scroll)
            self.is_running_ports = False

    @work(exclusive=True)
    async def _run_trace(self, host: str) -> None:
        """Ejecuta el traceroute en segundo plano y vuelca la salida al RichLog."""
        log = self.query_one("#trace-output", RichLog)
        self.is_running_trace = True

        log.clear()
        log.write(f"[bold white]⟶  Traceroute[/] → [cyan]{host}[/]")
        log.write(f"[dim]{'─' * 50}[/]")
        log.write("")

        self.trace_text_buffer = f"⟶  Traceroute → {host}\n──────────────────────────────────────────────────\n"

        try:
            async for line in red.traceroute_stream(host):
                colored = _colorize_trace(line)
                if colored:
                    log.write(colored)
                    self.trace_text_buffer += line + "\n"
        except asyncio.CancelledError:
            log.write("")
            log.write("[bold yellow]⏹  Traceroute detenido por el usuario.[/]")
            self.trace_text_buffer += "\n⏹  Traceroute detenido por el usuario.\n"
        finally:
            log.write("")
            log.write(f"[dim]{'─' * 50}[/]")
            log.write("[dim]Finalizado.  (Ctrl+L para limpiar)[/]")
            self.trace_text_buffer += f"\n──────────────────────────────────────────────────\nFinalizado.\n"
            self.is_running_trace = False

    # ── Worker asíncrono ───────────────────────────────────────────────────

    @work(exclusive=True)
    async def _run_ping(self, host: str, count: int) -> None:
        """
        Ejecuta el ping en segundo plano y vuelca la salida al RichLog.

        Al ser ``exclusive=True``, una nueva llamada cancela la anterior.
        Captura ``CancelledError`` para mostrar el mensaje de detención.
        """
        log = self.query_one("#ping-output", RichLog)
        self.is_running = True

        log.clear()
        log.write(
            f"[bold white]⟶  Ping[/] → [cyan]{host}[/]  "
            f"[dim]({count} paquetes)[/]"
        )
        log.write(f"[dim]{'─' * 50}[/]")
        log.write("")

        self.ping_text_buffer = f"⟶  Ping → {host} ({count} paquetes)\n──────────────────────────────────────────────────\n"

        try:
            async for line in red.ping_stream(host, count):
                colored = _colorize(line)
                if colored:
                    log.write(colored)
                    self.ping_text_buffer += line + "\n"

        except asyncio.CancelledError:
            log.write("")
            log.write("[bold yellow]⏹  Ping detenido por el usuario.[/]")
            self.ping_text_buffer += "\n⏹  Ping detenido por el usuario.\n"

        finally:
            log.write("")
            log.write(f"[dim]{'─' * 50}[/]")
            log.write("[dim]Finalizado.  (Ctrl+L para limpiar)[/]")
            self.ping_text_buffer += f"\n──────────────────────────────────────────────────\nFinalizado.\n"
            self.is_running = False

    # ── Worker asíncrono para Escáner LAN ───────────────────────────────────

    @work(exclusive=True)
    async def _run_lan(self, subnet: str) -> None:
        """Ejecuta el escaneo de red local en segundo plano y vuelca la salida al RichLog ordenado por IP."""
        import ipaddress
        log = self.query_one("#lan-output", RichLog)
        self.is_running_lan = True

        log.auto_scroll = False
        log.clear()
        log.write(f"[bold white]⟶  Escaneo de red local[/] → [cyan]{subnet}[/]")
        log.write(f"[dim]{'─' * 110}[/]")
        log.write("")

        self.lan_text_buffer = f"⟶  Escaneo de red local → {subnet}\n──────────────────────────────────────────────────────────────────────────────────────────────────────────────\n"

        # Cabecera de tabla
        table_header = "[bold white]IP[/]                     │ [bold white]MAC[/]               │ [bold white]Nombre de Host[/]                │ [bold white]Fabricante (MAC Vendor)[/]"
        log.write(table_header)
        log.write(f"[dim]{'─' * 110}[/]")

        active_hosts = []
        active_count = 0
        try:
            async for host in red.scan_local_network(subnet):
                if "error" in host:
                    log.write(f"[bold red]❌ {host['error']}[/]")
                    self.lan_text_buffer += f"Error: {host['error']}\n"
                    break
                
                active_hosts.append(host)
                active_count += 1
                
                # Ordenar por dirección IP de forma numérica
                try:
                    active_hosts.sort(key=lambda h: ipaddress.IPv4Address(h["ip"]))
                except Exception:
                    active_hosts.sort(key=lambda h: h["ip"])
                
                # Redibujar la tabla con el nuevo elemento ordenado
                log.clear()
                log.write(f"[bold white]⟶  Escaneo de red local[/] → [cyan]{subnet}[/]")
                log.write(f"[dim]{'─' * 110}[/]")
                log.write("")
                log.write(table_header)
                log.write(f"[dim]{'─' * 110}[/]")
                
                self.lan_text_buffer = f"⟶  Escaneo de red local → {subnet}\n──────────────────────────────────────────────────────────────────────────────────────────────────────────────\n"
                self.lan_text_buffer += "IP                     │ MAC               │ Nombre de Host                │ Fabricante (MAC Vendor)\n"
                self.lan_text_buffer += "──────────────────────────────────────────────────────────────────────────────────────────────────────────────\n"
                
                for h in active_hosts:
                    ip = h["ip"]
                    mac = h["mac"]
                    raw_host = h["hostname"] or "desconocido"
                    vendor = h.get("mac_vendor") or "Desconocido"
                    
                    ip_col = f"{ip:<22}"
                    mac_col = f"{mac:<17}"
                    host_col = f"{raw_host:<30}"
                    
                    if h["hostname"]:
                        host_rich = f"[white]{host_col}[/]"
                    else:
                        host_rich = f"[dim]{host_col}[/]"
                        
                    line_rich = f"[bright_green]{ip_col}[/] │ [cyan]{mac_col}[/] │ {host_rich} │ [yellow]{vendor}[/]"
                    line_plain = f"{ip_col} │ {mac_col} │ {host_col} │ {vendor}"
                    
                    log.write(line_rich)
                    self.lan_text_buffer += line_plain + "\n"
                    
                log.scroll_home(animate=False)

        except asyncio.CancelledError:
            log.auto_scroll = False
            log.write("")
            log.write("[bold yellow]⏹  Escaneo detenido por el usuario.[/]")
            self.lan_text_buffer += "\n⏹  Escaneo detenido por el usuario.\n"
        finally:
            log.write("")
            log.write(f"[dim]{'─' * 110}[/]")
            log.write(f"[bold green]✔ Completado. Se encontraron {active_count} dispositivos activos.[/]  (Ctrl+L para limpiar)")
            self.lan_text_buffer += f"\n──────────────────────────────────────────────────────────────────────────────────────────────────────────────\nCompletado. Se encontraron {active_count} dispositivos activos.\n"
            log.scroll_home(animate=False)
            def restore_scroll():
                log.auto_scroll = True
            self.call_after_refresh(restore_scroll)
            self.is_running_lan = False
