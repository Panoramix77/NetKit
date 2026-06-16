import re

with open("tui/interfaz.py", "r", encoding="utf-8") as f:
    content = f.read()

# Import Select
content = content.replace(
    "from textual.widgets import Footer, Static, Button, Input, RichLog, ContentSwitcher",
    "from textual.widgets import Footer, Static, Button, Input, RichLog, ContentSwitcher, Select"
)

# Reactive variables
content = content.replace(
    "    is_running_lan:   reactive[bool] = reactive(False)",
    "    is_running_lan:   reactive[bool] = reactive(False)\n    is_running_ports: reactive[bool] = reactive(False)"
)

# CSS rules
css_old = "    #ping-host, #trace-host, #lan-subnet {"
css_new = """    #ping-host, #trace-host, #lan-subnet, #ports-host {
        width: 1fr;
        margin-right: 1;
    }

    #ports-mode { width: 22; margin-right: 1; }
    #ports-custom { width: 20; margin-right: 1; }
    #ports-protocol { width: 12; margin-right: 1; }

    /* Fake selector to keep old format string working if needed */
    .dummy-placeholder {"""
content = content.replace(css_old, css_new)

# Sidebar
sidebar_old = 'yield Button("📡  Escáner LAN", id="btn-lan", classes="tool-btn")'
sidebar_new = 'yield Button("📡  Escáner LAN", id="btn-lan", classes="tool-btn")\n                yield Button("🛡️  Escáner Puertos", id="btn-ports", classes="tool-btn")'
content = content.replace(sidebar_old, sidebar_new)

# Content view
lan_view_end = 'yield RichLog(id="lan-output", classes="output-log", markup=True, highlight=False, wrap=True)'
ports_view = """yield RichLog(id="lan-output", classes="output-log", markup=True, highlight=False, wrap=True)

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
                        yield RichLog(id="ports-output", classes="output-log", markup=True, highlight=False, wrap=True)"""
content = content.replace(lan_view_end, ports_view)

# on_mount
mount_old = "self._lan_worker = None"
mount_new = "self._lan_worker = None\n        self._ports_worker = None"
content = content.replace(mount_old, mount_new)

# _show_welcome
calc_welcome_end = """log_calc.write("")
        except Exception:
            pass"""

ports_welcome = """log_calc.write("")
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
            log_ports.write("[dim]Descubre los puertos y servicios de un equipo remoto.[/]")
            log_ports.write("")
            log_ports.write("[bold white]Leyenda de Estados:[/]")
            log_ports.write("[bold green]  ● OPEN[/]          El puerto acepta conexiones.")
            log_ports.write("[bold yellow]  ● FILTERED[/]      Un firewall bloquea la respuesta.")
            log_ports.write("[bold red]  ● CLOSED[/]        Accesible pero sin servicio escuchando.")
            log_ports.write("[bold cyan]  ● OPEN|FILTERED[/] (UDP) Abierto o ignorado por firewall.")
            log_ports.write("")
            log_ports.write("[dim]Selecciona el modo y pulsa [bold white]▶ Escanear[/bold white].[/]")
            log_ports.write("")
        except Exception:
            pass"""
content = content.replace(calc_welcome_end, ports_welcome)

# Watch running ports
watch_lan = """    def watch_is_running_lan(self, running: bool) -> None:"""
watch_ports = """    def watch_is_running_ports(self, running: bool) -> None:
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

    def watch_is_running_lan(self, running: bool) -> None:"""
content = content.replace(watch_lan, watch_ports)

# Select changed
methods_end = """    def _execute_calc(self) -> None:"""
select_changed = """    def on_select_changed(self, event: Select.Changed) -> None:
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

        host = self.query_one("#ports-host", Input).value.strip()
        if not host:
            self.query_one("#ports-output", RichLog).write("[bold red]⚠  Introduce un host o IP.[/]")
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

        self._ports_worker = self._run_ports(host, ports, protocol)

    def _execute_calc(self) -> None:"""
content = content.replace(methods_end, select_changed)

# on_button_pressed
btn_lan = """            case "btn-lan":"""
btn_ports = """            case "btn-ports":
                self._switch_view("view-ports", event.button)
            case "btn-lan":"""
content = content.replace(btn_lan, btn_ports)

btn_run_lan = """            case "run-lan-btn":"""
btn_run_ports = """            case "run-ports-btn":
                self._execute_ports()
            case "run-lan-btn":"""
content = content.replace(btn_run_lan, btn_run_ports)

# Worker for ports
worker_trace = """    @work(exclusive=True)
    async def _run_trace(self, host: str) -> None:"""
worker_ports = """    @work(exclusive=True)
    async def _run_ports(self, host: str, ports: list[int], protocol: str) -> None:
        log = self.query_one("#ports-output", RichLog)
        self.is_running_ports = True

        log.clear()
        log.write(f"[bold white]⟶  Escaneando puertos ({protocol.upper()})[/] en [cyan]{host}[/]")
        log.write(f"[dim]{'─' * 60}[/]")
        log.write(f"[bold white]{'PUERTO':<10} {'ESTADO':<15} {'SERVICIO'}[/]")
        log.write(f"[dim]{'─' * 60}[/]")

        try:
            async for res in red.scan_ports_stream(host, ports, protocol):
                port = res["port"]
                state = res["state"]
                service = res["service"]
                
                if state == "OPEN":
                    color = "green"
                elif state == "FILTERED":
                    color = "yellow"
                elif state == "CLOSED":
                    color = "red"
                else:
                    color = "cyan"
                    
                log.write(f"{port:<10} [{color}]{state:<15}[/] {service}")
        except asyncio.CancelledError:
            log.write("")
            log.write("[bold yellow]⏹  Escaneo detenido por el usuario.[/]")
        finally:
            log.write("")
            log.write(f"[dim]{'─' * 60}[/]")
            log.write("[dim]Finalizado.  (Ctrl+L para limpiar)[/]")
            self.is_running_ports = False

    @work(exclusive=True)
    async def _run_trace(self, host: str) -> None:"""
content = content.replace(worker_trace, worker_ports)

# Save
with open("tui/interfaz.py", "w", encoding="utf-8") as f:
    f.write(content)

