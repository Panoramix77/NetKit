"""
Módulo de lógica de red pura.

Contiene funciones independientes de la interfaz para operaciones de red.
Cada función es asíncrona y multiplataforma (Windows / Linux / macOS).
"""
import asyncio
import platform
from typing import AsyncIterator


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _get_ping_command(host: str, count: int) -> list[str]:
    """
    Construye el comando ping apropiado para el sistema operativo actual.

    Args:
        host:  Hostname o dirección IP destino.
        count: Número de paquetes a enviar.

    Returns:
        Lista de tokens del comando listo para ``asyncio.create_subprocess_exec``.
    """
    system = platform.system().lower()
    if system == "windows":
        # Windows: ping -n <count> <host>
        return ["ping", "-n", str(count), host]
    else:
        # Linux/macOS: -c count, -W timeout por paquete (segundos)
        return ["ping", "-c", str(count), "-W", "2", host]


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

async def ping_stream(host: str, count: int = 4) -> AsyncIterator[str]:
    """
    Ejecuta ping contra un host y transmite la salida línea a línea.

    El subproceso se termina automáticamente si el generador se cierra
    antes de que el ping finalice (p. ej., por cancelación del worker).

    Args:
        host:  Hostname o dirección IP a hacer ping.
        count: Número de paquetes ICMP a enviar (por defecto 4, máx. 50).

    Yields:
        Cadenas de texto con cada línea de salida del ping.
    """
    count = max(1, min(50, count))
    cmd = _get_ping_command(host, count)
    process: asyncio.subprocess.Process | None = None

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        assert process.stdout is not None
        async for raw_line in process.stdout:
            yield raw_line.decode(errors="replace").rstrip()

        await process.wait()

    except FileNotFoundError:
        yield "ERROR: El comando 'ping' no está disponible en este sistema."
    except PermissionError:
        yield "ERROR: Permiso denegado. Intenta ejecutar como administrador."
    except Exception as exc:  # noqa: BLE001
        yield f"ERROR: {exc}"
    finally:
        # Garantiza que el subproceso se cierra aunque el generador sea cancelado
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                process.kill()


def get_active_interface_and_ip() -> tuple[str, str]:
    """
    Obtiene el nombre de la interfaz de red activa y su dirección IP.
    Intenta usar métodos nativos según el sistema operativo.
    """
    import subprocess
    import socket
    import re

    system = platform.system().lower()
    ip = "127.0.0.1"
    iface = "unknown"

    # Obtener IP local de la ruta por defecto usando UDP (funciona en todos)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # No requiere conexión real a internet para obtener la IP de la interfaz saliente
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    if system == "windows":
        try:
            # En Windows moderno, PowerShell es la forma más directa y fiable
            out = subprocess.check_output(
                ["powershell", "-Command", "Get-NetIPInterface -AddressFamily IPv4 | Where-Object {$_.InterfaceConnectionStatus -eq 'Connected'} | Select-Object -First 1 -ExpandProperty InterfaceAlias"],
                text=True,
                stderr=subprocess.DEVNULL
            )
            val = out.strip()
            if val:
                iface = val
        except Exception:
            try:
                out = subprocess.check_output(["netsh", "interface", "ipv4", "show", "interfaces"], text=True)
                for line in out.strip().split("\n"):
                    if "connected" in line.lower() or "conectado" in line.lower():
                        parts = line.split()
                        if len(parts) >= 5:
                            iface = " ".join(parts[4:])
                            break
            except Exception:
                iface = "Ethernet"
    else:
        # Linux / macOS
        try:
            out = subprocess.check_output(["ip", "route", "get", "8.8.8.8"], text=True)
            match_dev = re.search(r"dev\s+(\S+)", out)
            match_src = re.search(r"src\s+(\S+)", out)
            if match_dev:
                iface = match_dev.group(1)
            if match_src:
                ip = match_src.group(1)
        except Exception:
            try:
                # Fallback para macOS
                out = subprocess.check_output(["route", "-n", "get", "default"], text=True)
                match_dev = re.search(r"interface:\s+(\S+)", out)
                if match_dev:
                    iface = match_dev.group(1)
            except Exception:
                pass

    return iface, ip


def get_interfaces_info_linux() -> list[dict]:
    """
    Obtiene la información de las interfaces de red en sistemas Linux.
    """
    import subprocess
    import re
    try:
        out = subprocess.check_output(["ip", "addr"], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return []
    
    interfaces = []
    
    # Separar por bloques de interfaz (mirada hacia adelante de "índice: ")
    entries = re.split(r'\n(?=\d+:\s)', "\n" + out)
    for entry in entries:
        if not entry.strip():
            continue
        
        header_match = re.search(r'^\d+:\s+([^:]+):\s+<([^>]+)>(?:\s+mtu\s+\d+)?(?:\s+qdisc\s+\S+)?\s+state\s+(\S+)', entry, re.MULTILINE)
        if not header_match:
            name_match = re.search(r'^\d+:\s+([^:]+):', entry, re.MULTILINE)
            if not name_match:
                continue
            name = name_match.group(1).split("@")[0]  # Limpiar nombre veth o similar
            state = "UNKNOWN"
        else:
            name = header_match.group(1).split("@")[0]
            state = header_match.group(3)
        
        mac_match = re.search(r'link/ether\s+(\S+)', entry)
        mac = mac_match.group(1) if mac_match else "N/A"
        if "link/loopback" in entry:
            mac = "00:00:00:00:00:00"
        
        ipv4_list = re.findall(r'inet\s+(\S+)', entry)
        ipv6_list = re.findall(r'inet6\s+(\S+)', entry)
        
        # Limpiar estados de interfaces de red de Linux comunes
        status = state.upper()
        if "UP" in status or "LOWER_UP" in entry:
            status = "UP"
        elif "DOWN" in status:
            status = "DOWN"
        
        interfaces.append({
            "name": name,
            "status": status,
            "mac": mac,
            "ipv4": ipv4_list,
            "ipv6": ipv6_list
        })
    return interfaces


def get_interfaces_info_windows() -> list[dict]:
    """
    Obtiene la información de las interfaces de red en sistemas Windows usando PowerShell.
    """
    import subprocess
    import json
    
    interfaces = {}
    
    # 1. Obtener IP y familias de direcciones
    try:
        cmd_ips = 'powershell -Command "Get-NetIPAddress | Where-Object {$_.AddressState -eq \'Preferred\'} | Select-Object InterfaceAlias, IPAddress, AddressFamily, PrefixLength | ConvertTo-Json -Compress"'
        out_ips = subprocess.check_output(cmd_ips, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        if out_ips:
            data = json.loads(out_ips)
            if not isinstance(data, list):
                data = [data]
            for item in data:
                alias = item.get("InterfaceAlias")
                ip = item.get("IPAddress")
                family = item.get("AddressFamily")
                prefix = item.get("PrefixLength")
                
                if not alias or not ip:
                    continue
                # Ignorar IPs de loopback genéricas si se desea, o mantenerlas
                if alias not in interfaces:
                    interfaces[alias] = {"name": alias, "status": "UNKNOWN", "mac": "N/A", "ipv4": [], "ipv6": []}
                
                if family == 2:  # IPv4
                    ip_str = f"{ip}/{prefix}" if prefix is not None else ip
                    interfaces[alias]["ipv4"].append(ip_str)
                elif family == 23:  # IPv6
                    interfaces[alias]["ipv6"].append(ip)
    except Exception:
        pass
    
    # 2. Obtener estado de adaptadores y MAC
    try:
        cmd_adapters = 'powershell -Command "Get-NetAdapter | Select-Object Name, Status, MacAddress | ConvertTo-Json -Compress"'
        out_adapters = subprocess.check_output(cmd_adapters, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        if out_adapters:
            data = json.loads(out_adapters)
            if not isinstance(data, list):
                data = [data]
            for item in data:
                name = item.get("Name")
                status = str(item.get("Status", "UNKNOWN")).upper()
                mac = item.get("MacAddress", "N/A")
                
                if not name:
                    continue
                # Mapear estados a UP/DOWN
                if "UP" in status or "PROCEEDING" in status:
                    status_mapped = "UP"
                elif "DOWN" in status or "DISCONNECTED" in status:
                    status_mapped = "DOWN"
                else:
                    status_mapped = "UNKNOWN"
                
                if name in interfaces:
                    interfaces[name]["status"] = status_mapped
                    interfaces[name]["mac"] = mac
                else:
                    interfaces[name] = {
                        "name": name,
                        "status": status_mapped,
                        "mac": mac,
                        "ipv4": [],
                        "ipv6": []
                    }
    except Exception:
        pass
        
    return list(interfaces.values())


def get_interfaces_info() -> list[dict]:
    """
    Retorna la lista de todas las interfaces de red del sistema con su estado,
    dirección MAC, direcciones IPv4 e IPv6.
    """
    import platform
    system = platform.system().lower()
    if system == "windows":
        return get_interfaces_info_windows()
    else:
        return get_interfaces_info_linux()


async def traceroute_stream(host: str) -> AsyncIterator[str]:
    """
    Ejecuta el trazado de ruta (traceroute/tracert) de forma asíncrona,
    emitiendo la salida línea por línea.
    
    En Windows utiliza 'tracert'.
    En Linux intenta 'traceroute' y, si no está disponible, hace fallback a 'tracepath'.
    """
    import platform
    import asyncio
    
    system = platform.system().lower()
    cmd = ["tracert", host] if system == "windows" else ["traceroute", host]
    
    process: asyncio.subprocess.Process | None = None
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        if system != "windows":
            # Fallback a tracepath en Linux
            try:
                cmd = ["tracepath", host]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
            except FileNotFoundError:
                yield "ERROR: Los comandos 'traceroute' y 'tracepath' no están instalados. Instálalos usando el gestor de paquetes."
                return
        else:
            yield "ERROR: El comando 'tracert' no está disponible en este sistema."
            return

    assert process.stdout is not None
    async for raw_line in process.stdout:
        yield raw_line.decode(errors="replace").rstrip()

    await process.wait()


def _get_arp_table_linux() -> dict[str, str]:
    """Lee y parsea la tabla ARP local en Linux leyendo /proc/net/arp directamente."""
    arp_table = {}
    try:
        with open("/proc/net/arp", "r") as f:
            lines = f.readlines()
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 4:
                    ip = parts[0]
                    mac = parts[3]
                    if mac != "00:00:00:00:00:00":
                        arp_table[ip] = mac.lower()
    except Exception:
        pass
    return arp_table


def _get_arp_table_windows() -> dict[str, str]:
    """Ejecuta y parsea el comando arp -a en Windows."""
    import subprocess
    import re
    arp_table = {}
    try:
        out = subprocess.check_output(["arp", "-a"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+([0-9a-fA-F:-]{17})", line)
            if match:
                ip = match.group(1)
                mac = match.group(2).replace("-", ":").lower()
                arp_table[ip] = mac
    except Exception:
        pass
    return arp_table


def _get_arp_table() -> dict[str, str]:
    """Obtiene la tabla ARP del sistema actual en un diccionario {IP: MAC}."""
    system = platform.system().lower()
    if system == "windows":
        return _get_arp_table_windows()
    else:
        return _get_arp_table_linux()


async def _ping_host_quick(ip: str) -> bool:
    """Envía un único paquete ping rápido para comprobar la disponibilidad del host."""
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "1", "-w", "800", ip]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", ip]
        
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        return process.returncode == 0
    except Exception:
        return False


async def _resolve_hostname(ip: str) -> str:
    """
    Intenta resolver el nombre de host de una dirección IP de la red local
    usando múltiples métodos: DNS local, mDNS (Avahi/Bonjour) y NetBIOS.
    """
    import socket
    import subprocess
    import platform
    import re
    import asyncio
    
    # 1. Intentar resolver por DNS local / resolver del sistema
    loop = asyncio.get_running_loop()
    try:
        hostname_info = await loop.run_in_executor(None, socket.gethostbyaddr, ip)
        if hostname_info and hostname_info[0]:
            # Limpiar nombres largos de reverse DNS si tienen formato in-addr.arpa
            if not hostname_info[0].endswith(".in-addr.arpa"):
                return hostname_info[0]
    except Exception:
        pass

    system = platform.system().lower()
    if system == "linux":
        # 2. Intentar mDNS con avahi-resolve (común en Linux)
        try:
            process = await asyncio.create_subprocess_exec(
                "avahi-resolve", "-a", ip,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0 and stdout:
                line = stdout.decode(errors="replace").strip()
                # Salida esperada: "192.168.1.53\tname.local"
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1]
        except FileNotFoundError:
            pass
        except Exception:
            pass

        # 3. Intentar NetBIOS con nmblookup (herramienta de Samba en Linux)
        try:
            process = await asyncio.create_subprocess_exec(
                "nmblookup", "-A", ip,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0 and stdout:
                # Buscar líneas que contengan el nombre del host (primera palabra en líneas tabuladas)
                for line in stdout.decode(errors="replace").splitlines():
                    line = line.strip()
                    if line and not line.startswith("Looking up") and not line.startswith("Attributes"):
                        match = re.match(r"^([A-Za-z0-9_-]+)\s+<\d+>", line)
                        if match:
                            return match.group(1)
        except FileNotFoundError:
            pass
        except Exception:
            pass

    return ""


def detect_local_subnets() -> list[str]:
    """Detecta las subredes IPv4 activas en el sistema."""
    import ipaddress
    subnets = []
    for iface in get_interfaces_info():
        # Considerar interfaces activas y no loopback
        if iface["name"] == "lo" or iface["name"] == "loopback":
            continue
        for ip_mask in iface.get("ipv4", []):
            try:
                if "/" in ip_mask:
                    net = ipaddress.IPv4Interface(ip_mask).network
                else:
                    net = ipaddress.IPv4Interface(f"{ip_mask}/24").network
                if not net.is_loopback:
                    subnets.append(str(net))
            except Exception:
                pass
    return list(set(subnets))


async def scan_local_network(subnet: str) -> AsyncIterator[dict]:
    """
    Escanea una subred enviando pings asíncronos concurrentes.
    Yields un diccionario por cada host activo encontrado:
    {
        "ip": "192.168.1.1",
        "hostname": "nombre-del-equipo",
        "mac": "00:11:22:33:44:55",
        "status": "active"
    }
    """
    import ipaddress
    
    try:
        network = ipaddress.IPv4Network(subnet, strict=False)
    except ValueError:
        yield {"error": f"Subred inválida: {subnet}"}
        return

    # Obtener tabla ARP inicial
    arp_table = _get_arp_table()
    hosts = list(network.hosts())
    if not hosts:
        hosts = [network.network_address]

    semaphore = asyncio.Semaphore(60)  # Limitar la concurrencia a 60 pings simultáneos
    queue = asyncio.Queue()

    async def worker(ip_obj):
        ip_str = str(ip_obj)
        async with semaphore:
            active = await _ping_host_quick(ip_str)
            if active:
                hostname = await _resolve_hostname(ip_str)
                # Volver a leer la tabla ARP para capturar la MAC recién resuelta
                local_arp = _get_arp_table()
                mac = local_arp.get(ip_str, arp_table.get(ip_str, "N/A"))
                vendor = get_mac_vendor(mac)
                await queue.put({
                    "ip": ip_str,
                    "hostname": hostname,
                    "mac": mac,
                    "mac_vendor": vendor,
                    "status": "active"
                })
            else:
                await queue.put({"ip": ip_str, "status": "inactive"})

    # Lanzar los workers
    tasks = [asyncio.create_task(worker(h)) for h in hosts]

    pending_count = len(hosts)
    while pending_count > 0:
        result = await queue.get()
        pending_count -= 1
        if result.get("status") == "active":
            yield result


def to_ipcalc_binary(ip_str: str, prefix_len: int) -> str:
    """Formatea la IP a binario con un espacio separador después del prefix_len-ésimo bit."""
    octets = [int(o) for o in ip_str.split('.')]
    binary_32 = ''.join(f'{o:08b}' for o in octets)
    
    if 0 < prefix_len < 32:
        network_part = binary_32[:prefix_len]
        host_part = binary_32[prefix_len:]
    else:
        network_part = binary_32
        host_part = ""
        
    result = []
    bit_index = 0
    
    for char in network_part:
        if bit_index > 0 and bit_index % 8 == 0:
            result.append('.')
        result.append(char)
        bit_index += 1
        
    if 0 < prefix_len < 32:
        result.append(' ')
        
    for char in host_part:
        if bit_index > 0 and bit_index % 8 == 0:
            result.append('.')
        result.append(char)
        bit_index += 1
        
    return ''.join(result)


def to_ipcalc_binary_network(ip_str: str, prefix_len: int, class_prefix_len: int) -> str:
    """Formatea la IP de red con el split de clase y el split de subred en binario."""
    octets = [int(o) for o in ip_str.split('.')]
    binary_32 = ''.join(f'{o:08b}' for o in octets)
    
    split_indices = set()
    if 0 < class_prefix_len < 32:
        split_indices.add(class_prefix_len)
    if 0 < prefix_len < 32:
        split_indices.add(prefix_len)
        
    result = []
    bit_index = 0
    
    for char in binary_32:
        if bit_index > 0 and bit_index % 8 == 0:
            result.append('.')
        result.append(char)
        bit_index += 1
        
        if bit_index in split_indices:
            result.append(' ')
            
    return ''.join(result)


def get_class_info(ip_str: str) -> tuple[str, int]:
    """Obtiene el nombre de la clase IPv4 y su longitud de prefijo estándar."""
    try:
        first_octet = int(ip_str.split('.')[0])
        if 1 <= first_octet <= 127:
            return "Class A", 1
        elif 128 <= first_octet <= 191:
            return "Class B", 2
        elif 192 <= first_octet <= 223:
            return "Class C", 3
        elif 224 <= first_octet <= 239:
            return "Class D", 4
        elif 240 <= first_octet <= 255:
            return "Class E", 5
    except Exception:
        pass
    return "Unknown", 0


def is_private_ip(ip_str: str) -> bool:
    """Comprueba si la dirección IP pertenece a rangos privados RFC 1918."""
    import ipaddress
    try:
        ip = ipaddress.IPv4Address(ip_str)
        if ip in ipaddress.IPv4Network("10.0.0.0/8"):
            return True
        if ip in ipaddress.IPv4Network("172.16.0.0/12"):
            return True
        if ip in ipaddress.IPv4Network("192.168.0.0/16"):
            return True
    except Exception:
        pass
    return False


def calculate_subnet(ip_val: str, mask1_val: str = None, mask2_val: str = None) -> dict:
    """
    Calcula la información de subred al estilo de jodies.de/ipcalc.
    ip_val: IP, IP/prefijo o IP máscara (separado por espacio).
    mask1_val: Máscara principal (opcional si ip_val contiene /máscara).
    mask2_val: Máscara secundaria opcional para sub/superred.
    """
    import ipaddress
    
    ip_part = ip_val.strip()
    mask1_part = mask1_val.strip() if mask1_val else None
    mask2_part = mask2_val.strip() if mask2_val else None
    
    # Si la IP incluye / prefijo
    if "/" in ip_part:
        parts = ip_part.split("/")
        ip_part = parts[0].strip()
        if not mask1_part:
            mask1_part = parts[1].strip()
            
    # Si la IP contiene espacio
    elif " " in ip_part or "\t" in ip_part:
        parts = [p.strip() for p in ip_part.replace("\t", " ").split(" ") if p.strip()]
        if len(parts) >= 2:
            ip_part = parts[0]
            if not mask1_part:
                mask1_part = parts[1]
                
    # Validar IP
    try:
        ip_obj = ipaddress.IPv4Address(ip_part)
    except Exception as e:
        return {"success": False, "error": f"Dirección IP inválida: {e}"}
        
    # Validar o deducir Máscara 1
    prefix_len = 24
    if mask1_part:
        if mask1_part.isdigit():
            prefix_len = int(mask1_part)
        elif mask1_part.startswith("/") and mask1_part[1:].isdigit():
            prefix_len = int(mask1_part[1:])
        else:
            try:
                # Comprobar si es wildcard / máscara inversa
                octets = [int(x) for x in mask1_part.split('.')]
                if len(octets) == 4:
                    if octets[0] < 128:
                        mask_val = int(ipaddress.IPv4Address(mask1_part))
                        subnet_val = mask_val ^ 0xffffffff
                        subnet_ip = ipaddress.IPv4Address(subnet_val)
                        net = ipaddress.IPv4Network(f"0.0.0.0/{subnet_ip}", strict=False)
                        prefix_len = net.prefixlen
                    else:
                        net = ipaddress.IPv4Network(f"0.0.0.0/{mask1_part}", strict=False)
                        prefix_len = net.prefixlen
            except Exception:
                try:
                    net = ipaddress.IPv4Network(f"0.0.0.0/{mask1_part}", strict=False)
                    prefix_len = net.prefixlen
                except Exception as e:
                    return {"success": False, "error": f"Máscara 1 inválida: {e}"}
    else:
        # Default mask by class
        first_octet = int(str(ip_obj).split('.')[0])
        if 1 <= first_octet <= 127:
            prefix_len = 8
        elif 128 <= first_octet <= 191:
            prefix_len = 16
        elif 192 <= first_octet <= 223:
            prefix_len = 24
        else:
            prefix_len = 24
            
    if prefix_len < 0 or prefix_len > 32:
        return {"success": False, "error": "El prefijo de Máscara 1 debe estar entre 0 y 32"}
        
    # Validar Máscara 2 opcional
    mask2_prefix_len = None
    if mask2_part:
        if mask2_part.isdigit():
            mask2_prefix_len = int(mask2_part)
        elif mask2_part.startswith("/") and mask2_part[1:].isdigit():
            mask2_prefix_len = int(mask2_part[1:])
        else:
            try:
                octets = [int(x) for x in mask2_part.split('.')]
                if len(octets) == 4:
                    if octets[0] < 128:
                        mask_val = int(ipaddress.IPv4Address(mask2_part))
                        subnet_val = mask_val ^ 0xffffffff
                        subnet_ip = ipaddress.IPv4Address(subnet_val)
                        net = ipaddress.IPv4Network(f"0.0.0.0/{subnet_ip}", strict=False)
                        mask2_prefix_len = net.prefixlen
                    else:
                        net = ipaddress.IPv4Network(f"0.0.0.0/{mask2_part}", strict=False)
                        mask2_prefix_len = net.prefixlen
            except Exception:
                try:
                    net = ipaddress.IPv4Network(f"0.0.0.0/{mask2_part}", strict=False)
                    mask2_prefix_len = net.prefixlen
                except Exception as e:
                    return {"success": False, "error": f"Máscara 2 inválida: {e}"}
                    
        if mask2_prefix_len is not None and (mask2_prefix_len < 0 or mask2_prefix_len > 32):
            return {"success": False, "error": "El prefijo de Máscara 2 debe estar entre 0 y 32"}
            
    try:
        # Calcular red principal
        network = ipaddress.IPv4Network(f"{ip_part}/{prefix_len}", strict=False)
        netmask = str(network.netmask)
        wildcard = str(ipaddress.IPv4Address(int(network.netmask) ^ 0xffffffff))
        net_addr = str(network.network_address)
        broad_addr = str(network.broadcast_address)
        
        if prefix_len == 32:
            host_min = str(ip_obj)
            host_max = str(ip_obj)
            hosts_count = 1
        elif prefix_len == 31:
            host_min = broad_addr
            host_max = net_addr
            hosts_count = 0
        else:
            host_min = str(network.network_address + 1)
            host_max = str(network.broadcast_address - 1)
            hosts_count = 2 ** (32 - prefix_len) - 2
            
        class_name, class_prefix_len = get_class_info(str(ip_obj))
        
        binary_ip = to_ipcalc_binary(str(ip_obj), prefix_len)
        binary_mask = to_ipcalc_binary(netmask, prefix_len)
        binary_wildcard = to_ipcalc_binary(wildcard, prefix_len)
        binary_network = to_ipcalc_binary_network(net_addr, prefix_len, class_prefix_len)
        binary_broadcast = to_ipcalc_binary(broad_addr, prefix_len)
        binary_host_min = to_ipcalc_binary(host_min, prefix_len)
        binary_host_max = to_ipcalc_binary(host_max, prefix_len)
        
        network_comment = f"( {class_name} )" if class_name != "Unknown" else ""
        private_comment = " ( Private Internet )" if is_private_ip(str(ip_obj)) else ""
        
        result = {
            "success": True,
            "ip": str(ip_obj),
            "prefix_len": prefix_len,
            "netmask": netmask,
            "wildcard": wildcard,
            "network": net_addr,
            "broadcast": broad_addr,
            "host_min": host_min,
            "host_max": host_max,
            "hosts_count": f"{hosts_count}",
            "binary_ip": binary_ip,
            "binary_mask": binary_mask,
            "binary_wildcard": binary_wildcard,
            "binary_network": binary_network,
            "binary_broadcast": binary_broadcast,
            "binary_host_min": binary_host_min,
            "binary_host_max": binary_host_max,
            "network_comment": network_comment,
            "private_comment": private_comment,
            "mask2_prefix_len": mask2_prefix_len
        }
        
        # Subnetting / Supernetting
        if mask2_prefix_len is not None:
            if mask2_prefix_len > prefix_len:
                # Subnetting
                num_subnets = 2 ** (mask2_prefix_len - prefix_len)
                subnet_size = 2 ** (32 - mask2_prefix_len)
                parent_net_addr_int = int(network.network_address)
                
                sub_netmask = str(ipaddress.IPv4Network(f"0.0.0.0/{mask2_prefix_len}").netmask)
                sub_wildcard = str(ipaddress.IPv4Address(int(ipaddress.IPv4Network(f"0.0.0.0/{mask2_prefix_len}").netmask) ^ 0xffffffff))
                
                subnets_list = []
                limit_subnets = min(num_subnets, 64)
                for i in range(limit_subnets):
                    sub_net_addr_int = parent_net_addr_int + i * subnet_size
                    sub_net_addr = ipaddress.IPv4Address(sub_net_addr_int)
                    sub_net = ipaddress.IPv4Network(f"{sub_net_addr}/{mask2_prefix_len}")
                    
                    sub_net_addr_str = str(sub_net.network_address)
                    sub_broad_addr_str = str(sub_net.broadcast_address)
                    
                    if mask2_prefix_len == 32:
                        sub_host_min = sub_net_addr_str
                        sub_host_max = sub_net_addr_str
                        sub_hosts_count = 1
                    elif mask2_prefix_len == 31:
                        sub_host_min = sub_broad_addr_str
                        sub_host_max = sub_net_addr_str
                        sub_hosts_count = 0
                    else:
                        sub_host_min = str(sub_net.network_address + 1)
                        sub_host_max = str(sub_net.broadcast_address - 1)
                        sub_hosts_count = 2 ** (32 - mask2_prefix_len) - 2
                        
                    subnets_list.append({
                        "network": sub_net_addr_str,
                        "broadcast": sub_broad_addr_str,
                        "host_min": sub_host_min,
                        "host_max": sub_host_max,
                        "hosts_count": f"{sub_hosts_count}",
                        "binary_network": to_ipcalc_binary_network(sub_net_addr_str, mask2_prefix_len, class_prefix_len),
                        "binary_broadcast": to_ipcalc_binary(sub_broad_addr_str, mask2_prefix_len),
                        "binary_host_min": to_ipcalc_binary(sub_host_min, mask2_prefix_len),
                        "binary_host_max": to_ipcalc_binary(sub_host_max, mask2_prefix_len),
                        "private_comment": " ( Private Internet )" if is_private_ip(sub_net_addr_str) else ""
                    })
                    
                total_hosts = num_subnets * (2 ** (32 - mask2_prefix_len) - 2 if mask2_prefix_len <= 30 else (1 if mask2_prefix_len == 32 else 0))
                result["subnetting"] = {
                    "num_subnets": num_subnets,
                    "total_hosts": total_hosts,
                    "netmask": sub_netmask,
                    "wildcard": sub_wildcard,
                    "binary_mask": to_ipcalc_binary(sub_netmask, mask2_prefix_len),
                    "binary_wildcard": to_ipcalc_binary(sub_wildcard, mask2_prefix_len),
                    "subnets": subnets_list,
                    "limit_reached": num_subnets > limit_subnets
                }
                
            elif mask2_prefix_len < prefix_len:
                # Supernetting
                super_net = ipaddress.IPv4Network(f"{ip_part}/{mask2_prefix_len}", strict=False)
                super_netmask = str(super_net.netmask)
                super_wildcard = str(ipaddress.IPv4Address(int(super_net.netmask) ^ 0xffffffff))
                super_net_addr = str(super_net.network_address)
                super_broad_addr = str(super_net.broadcast_address)
                
                if mask2_prefix_len == 32:
                    super_host_min = super_net_addr
                    super_host_max = super_net_addr
                    super_hosts_count = 1
                elif mask2_prefix_len == 31:
                    super_host_min = super_broad_addr
                    super_host_max = super_net_addr
                    super_hosts_count = 0
                else:
                    super_host_min = str(super_net.network_address + 1)
                    super_host_max = str(super_net.broadcast_address - 1)
                    super_hosts_count = 2 ** (32 - mask2_prefix_len) - 2
                    
                result["supernetting"] = {
                    "netmask": super_netmask,
                    "wildcard": super_wildcard,
                    "network": super_net_addr,
                    "broadcast": super_broad_addr,
                    "host_min": super_host_min,
                    "host_max": super_host_max,
                    "hosts_count": f"{super_hosts_count}",
                    "binary_mask": to_ipcalc_binary(super_netmask, mask2_prefix_len),
                    "binary_wildcard": to_ipcalc_binary(super_wildcard, mask2_prefix_len),
                    "binary_network": to_ipcalc_binary_network(super_net_addr, mask2_prefix_len, class_prefix_len),
                    "binary_broadcast": to_ipcalc_binary(super_broad_addr, mask2_prefix_len),
                    "binary_host_min": to_ipcalc_binary(super_host_min, mask2_prefix_len),
                    "binary_host_max": to_ipcalc_binary(super_host_max, mask2_prefix_len),
                    "private_comment": " ( Private Internet )" if is_private_ip(super_net_addr) else ""
                }
                
        return result
    except Exception as e:
        return {"success": False, "error": f"Error de cálculo: {e}"}


_MAC_VENDORS_CACHE = None

def get_mac_vendor(mac: str) -> str:
    """
    Resuelve el fabricante (Vendor) de una dirección MAC usando la base de datos offline.
    
    Args:
        mac: La dirección MAC a resolver.
        
    Returns:
        El nombre del fabricante (Vendor) o 'Desconocido'/'N/A'.
    """
    global _MAC_VENDORS_CACHE
    if not mac or mac == "N/A":
        return "N/A"
        
    # Limpiar MAC y extraer el OUI (primeros 6 caracteres hexadecimales)
    import re
    clean_mac = re.sub(r'[^0-9A-Fa-f]', '', mac).upper()
    if len(clean_mac) < 6:
        return "N/A"
    oui = clean_mac[:6]
    
    if _MAC_VENDORS_CACHE is None:
        import json
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(current_dir, "mac_vendors.json")
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                _MAC_VENDORS_CACHE = json.load(f)
        except Exception:
            _MAC_VENDORS_CACHE = {}
            
    return _MAC_VENDORS_CACHE.get(oui, "Desconocido")




# ---------------------------------------------------------------------------
# Escáner de Puertos
# ---------------------------------------------------------------------------

UDP_PAYLOADS = {
    53: b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07version\x04bind\x00\x00\x10\x00\x03",
    123: b"\x1b" + 47 * b"\0",
    161: b"\x30\x26\x02\x01\x01\x04\x06\x70\x75\x62\x6c\x69\x63\xa0\x19\x02\x04\x0a\x6e\x67\x6b\x02\x01\x00\x02\x01\x00\x30\x0b\x30\x09\x06\x05\x2b\x06\x01\x02\x01\x05\x00",
    137: b"\x12\x34\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x20\x43\x4b\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41\x00\x00\x21\x00\x01"
}

def get_service_name(port: int, protocol: str) -> str:
    import socket
    try:
        return socket.getservbyport(port, protocol.lower())
    except Exception:
        # Fallback para comunes si no están en el sistema
        common = {
            21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "domain",
            80: "http", 110: "pop3", 111: "rpcbind", 135: "msrpc", 139: "netbios-ssn",
            143: "imap", 443: "https", 445: "microsoft-ds", 993: "imaps", 995: "pop3s",
            1723: "pptp", 3306: "mysql", 3389: "ms-wbt-server", 5900: "vnc", 8080: "http-proxy"
        }
        return common.get(port, "unknown")

async def scan_port(ip: str, port: int, protocol: str = "TCP", timeout: float = 1.0) -> dict:
    """
    Escanea un puerto específico (TCP o UDP).
    Retorna un diccionario con port, protocol, state y service.
    """
    import asyncio
    state = "UNKNOWN"
    if protocol.upper() == "TCP":
        try:
            conn = asyncio.open_connection(ip, port)
            reader, writer = await asyncio.wait_for(conn, timeout=timeout)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            state = "OPEN"
        except asyncio.TimeoutError:
            state = "FILTERED"
        except ConnectionRefusedError:
            state = "CLOSED"
        except Exception:
            state = "CLOSED"
    elif protocol.upper() == "UDP":
        payload = UDP_PAYLOADS.get(port, b"\x00\x01\x02\x03\r\n")
        
        class UDPProtocol(asyncio.DatagramProtocol):
            def __init__(self):
                self.transport = None
                self.response_received = asyncio.Event()
                self.error_received_event = asyncio.Event()

            def connection_made(self, transport):
                self.transport = transport
                transport.sendto(payload)

            def datagram_received(self, data, addr):
                self.response_received.set()

            def error_received(self, exc):
                self.error_received_event.set()
                
        loop = asyncio.get_running_loop()
        try:
            transport, protocol_inst = await loop.create_datagram_endpoint(
                lambda: UDPProtocol(),
                remote_addr=(ip, port)
            )
            
            tasks = [
                asyncio.create_task(protocol_inst.response_received.wait()),
                asyncio.create_task(protocol_inst.error_received_event.wait())
            ]
            done, pending = await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            
            for task in pending:
                task.cancel()
                
            if not done:
                state = "OPEN|FILTERED"
            elif protocol_inst.response_received.is_set():
                state = "OPEN"
            elif protocol_inst.error_received_event.is_set():
                state = "CLOSED"
            else:
                state = "OPEN|FILTERED"
            transport.close()
        except Exception:
            state = "CLOSED"
            
    service = get_service_name(port, protocol)
    return {"ip": ip, "port": port, "protocol": protocol.upper(), "state": state, "service": service}

async def scan_ports_stream(ips: list[str], ports: list[int], protocol: str = "TCP", timeout: float = 1.0, max_concurrency: int = 500) -> AsyncIterator[dict]:
    """
    Escanea una lista de puertos contra una lista de IPs, cediendo resultados a medida que se completan.
    """
    import asyncio
    semaphore = asyncio.Semaphore(max_concurrency)
    queue = asyncio.Queue()
    
    async def worker(ip: str, port: int):
        async with semaphore:
            result = await scan_port(ip, port, protocol, timeout)
            await queue.put(result)
            
    tasks = [asyncio.create_task(worker(i, p)) for i in ips for p in ports]
    
    pending = len(tasks)
    while pending > 0:
        result = await queue.get()
        pending -= 1
        yield result
        
    for task in tasks:
        task.cancel()

def parse_target_ips(target: str) -> list[str]:
    """Convierte una cadena de destino (IP, CIDR, Rango, o lista por comas) en una lista de IPs."""
    import ipaddress
    target = target.strip()
    if not target:
        return []
        
    ips = []
    current_prefix = ""
    
    parts = [p.strip() for p in target.split(",")]
    
    for part in parts:
        if not part: continue
        
        if "/" in part:
            try:
                net = ipaddress.IPv4Network(part, strict=False)
                if net.prefixlen >= 31:
                    ips.extend([str(ip) for ip in net])
                else:
                    ips.extend([str(ip) for ip in net.hosts()])
                octets = str(net.network_address).split(".")
                current_prefix = ".".join(octets[:3]) + "."
            except ValueError:
                pass
            continue
            
        if "-" in part:
            rng_parts = part.split("-", 1)
            start_str = rng_parts[0].strip()
            end_str = rng_parts[1].strip()
            
            if start_str.isdigit() and current_prefix:
                start_str = current_prefix + start_str
                
            try:
                start_ip = ipaddress.IPv4Address(start_str)
                start_octets = str(start_ip).split(".")
                current_prefix = ".".join(start_octets[:3]) + "."
                
                if end_str.isdigit():
                    end_octets = start_str.split(".")
                    end_octets[-1] = end_str
                    end_ip = ipaddress.IPv4Address(".".join(end_octets))
                else:
                    end_ip = ipaddress.IPv4Address(end_str)
                    
                start_int = int(start_ip)
                end_int = int(end_ip)
                
                if start_int <= end_int:
                    limit = min(end_int + 1, start_int + 65536)
                    for i in range(start_int, limit):
                        ips.append(str(ipaddress.IPv4Address(i)))
            except Exception:
                pass
            continue
            
        if part.isdigit() and current_prefix:
            part = current_prefix + part
            
        try:
            ip_obj = ipaddress.IPv4Address(part)
            ips.append(str(ip_obj))
            octets = str(ip_obj).split(".")
            current_prefix = ".".join(octets[:3]) + "."
        except Exception:
            ips.append(part)
            
    seen = set()
    result = []
    for ip in ips:
        if ip not in seen:
            seen.add(ip)
            result.append(ip)
            
    return result

def get_top_ports() -> list[int]:
    """Retorna los 100 puertos más comunes aproximados."""
    return [
        20, 21, 22, 23, 25, 53, 67, 68, 69, 80, 110, 111, 119, 123, 135, 137, 138, 139, 143, 161,
        162, 389, 443, 445, 465, 500, 514, 515, 520, 587, 631, 636, 873, 990, 993, 995, 1025, 1080,
        1194, 1433, 1434, 1521, 1723, 1812, 1813, 2049, 2121, 2483, 2484, 3128, 3306, 3389, 4500,
        4899, 5000, 5060, 5061, 5222, 5432, 5631, 5632, 5800, 5900, 5901, 5985, 5986, 6000, 6379,
        6667, 7000, 8000, 8008, 8080, 8443, 8888, 9000, 9090, 9100, 9418, 9999, 10000, 11211,
        27017, 27018, 31337, 32768, 49152, 49153, 49154, 49155, 49156, 49157, 50000
    ]

def get_port_list(mode: str) -> list[int]:
    if mode == "top100":
        return get_top_ports()
    elif mode == "all":
        return list(range(1, 65536))
    return [80, 443]

