# NetKit v0.2 — Panel de Control de Red TUI

> Herramienta interactiva de diagnóstico y administración de redes desde la terminal.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Textual](https://img.shields.io/badge/TUI-Textual-brightgreen)
![Licencia](https://img.shields.io/badge/Licencia-Privada-orange)
![Versión](https://img.shields.io/badge/Versión-0.2-blueviolet)

---

## 📖 Descripción

**NetKit** es un panel de control de red completo que se ejecuta directamente en la terminal. Diseñado como una TUI (Terminal User Interface), ofrece un dashboard interactivo con múltiples herramientas de diagnóstico de red integradas en una única interfaz visual.

Su arquitectura modular separa radicalmente la capa de presentación (`tui/`) de la lógica de red (`core/`), lo que permite mantener, ampliar y reutilizar cada módulo de forma independiente.

---

## ✨ Características

### 📋 Interfaces
Muestra información detallada de **todas las interfaces de red** del sistema (físicas y virtuales): nombre, estado (UP/DOWN), dirección MAC, direcciones IPv4 e IPv6.

### 🧮 Calculadora de Subredes
Calculadora IP completa compatible con el formato de [jodies.de/ipcalc](https://jodies.de/ipcalc):
- Entrada de IP + máscara en formato CIDR o decimal.
- Máscara secundaria opcional para calcular **sub/superredes**.
- Campos calculados: dirección de red, broadcast, rango de hosts, wildcard, clase de red y representación binaria con separadores de frontera exactos.

### 🌐 Ping
Verificación de conectividad y latencia contra cualquier host o IP:
- Número configurable de paquetes (1–50).
- Salida coloreada en tiempo real con indicadores visuales de éxito, error, timeout y estadísticas.

### 🔍 Traceroute
Trazador de rutas asíncrono que analiza los saltos intermedios hasta un destino:
- Soporte para `traceroute` y fallback a `tracepath` en Linux.
- Soporte para `tracert` en Windows.
- Salida coloreada con IPs resaltadas en verde y tiempos en cian.

### 📡 Escáner LAN
Descubrimiento rápido de dispositivos activos en la red local:
- **Ping sweep en paralelo** con límite de 60 conexiones simultáneas.
- **Ordenación numérica de IP** en tiempo real.
- **Resolución de hostname** mediante DNS local, mDNS (Avahi/Bonjour) y NetBIOS (nmblookup).
- **Consulta offline de fabricante MAC (Vendor)** con base de datos integrada de +52.000 entradas OUI.
- Detección automática de la subred activa al iniciar.

### 🛡️ Escáner de Puertos
Herramienta avanzada para descubrir puertos abiertos y servicios:
- **Escaneo asíncrono y ultra-rápido** de puertos TCP y UDP.
- **Inteligencia de destinos:** escanea IPs individuales, rangos (`192.168.1.1-20`), subredes (`10.0.0.0/24`) o listas abreviadas de hosts.
- **Agrupación automática** por Host, integrando resolución de nombre de dominio y fabricante MAC de la tarjeta de red.
- **Detección inteligente de estados:** diferencia claramente entre `OPEN`, `FILTERED`, `CLOSED` y `OPEN|FILTERED`.

---

## 🖥️ Capturas de pantalla

*(Ejecuta `python app.py` para ver la interfaz en acción directamente en tu terminal.)*

---

## 📂 Estructura del Proyecto

```text
NetKit/
├── app.py              # Punto de entrada principal (Arranca la TUI)
├── requirements.txt    # Dependencias del proyecto
├── agents.md           # Archivo de contexto para agentes IA
├── tui/
│   ├── __init__.py
│   └── interfaz.py     # Capa visual: menús, botones, formularios y eventos (Textual)
└── core/
    ├── __init__.py
    ├── red.py           # Capa de lógica: funciones puras de red (multiplataforma)
    └── mac_vendors.json # Base de datos offline de fabricantes MAC (OUI IEEE)
```

---

## 🚀 Instalación y Uso

### Requisitos previos
- **Python 3.10** o superior.
- Sistema operativo **Linux** o **Windows**.

### Instalación

```bash
# Clonar el repositorio
git clone https://gitea.ast3rix.myds.me/panoramix/NetKit.git
cd NetKit

# Crear entorno virtual (recomendado)
python -m venv .venv
source .venv/bin/activate   # Linux
# .venv\Scripts\activate    # Windows

# Instalar dependencias
pip install -r requirements.txt
```

### Ejecución

```bash
python app.py
```

### Atajos de teclado

| Atajo     | Acción                                    |
|-----------|-------------------------------------------|
| `q`       | Salir de la aplicación                    |
| `Ctrl+L`  | Limpiar los logs y restaurar la bienvenida|
| `Enter`   | Ejecutar la herramienta activa            |

---

## 🔧 Dependencias

| Paquete    | Versión mínima | Descripción                              |
|------------|----------------|------------------------------------------|
| `textual`  | ≥ 0.80.0       | Framework TUI para Python (Rich + async) |

### Herramientas del sistema (opcionales, mejoran funcionalidad)

| Herramienta    | Uso                                               |
|----------------|----------------------------------------------------|
| `traceroute`   | Trazado de rutas (fallback: `tracepath`)            |
| `avahi-resolve`| Resolución de nombres mDNS en red local             |
| `nmblookup`    | Resolución de nombres NetBIOS (paquete `samba`)     |

---

## 🏗️ Arquitectura

NetKit sigue el principio de **separación de responsabilidades**:

```
┌─────────────────────────────────────────────┐
│              app.py (Entrada)               │
└──────────────────┬──────────────────────────┘
                   │
       ┌───────────▼───────────┐
       │   tui/interfaz.py     │  ← Presentación (Textual TUI)
       │   - Layout y CSS      │
       │   - Eventos y widgets │
       │   - Workers async     │
       └───────────┬───────────┘
                   │ importa
       ┌───────────▼───────────┐
       │   core/red.py         │  ← Lógica pura de red
       │   - ping_stream()     │
       │   - traceroute_stream()│
       │   - scan_local_network()│
       │   - calculate_ipcalc()│
       │   - get_mac_vendor()  │
       └───────────────────────┘
```

- **`tui/interfaz.py`**: Toda la capa visual. No contiene lógica de red directa.
- **`core/red.py`**: Funciones puras y asíncronas. No depende de Textual ni de ningún framework visual.
- **`core/mac_vendors.json`**: Base de datos estática de prefijos OUI (IEEE) para resolución offline del fabricante de tarjetas de red.

---

## 🌐 Compatibilidad

| Sistema Operativo | Estado       |
|--------------------|-------------|
| Linux (Arch, Debian, Ubuntu…) | ✅ Completo |
| Windows 10/11      | ✅ Completo |
| macOS              | ⚠️ Parcial (no probado)  |

---

## 📋 Registro de cambios

### v0.2 — Herramientas Avanzadas y Mejoras TUI
- **Nuevo:** Escáner de Puertos asíncrono implementado.
- **Nuevo:** Motor de destinos (acepta rangos, subredes, listas con comas).
- **Mejora:** Rediseño visual de la tabla de visualización de interfaces.
- **Mejora:** Integración de nombres de host y MACs en el Escáner de Puertos.
- **UI:** Añadido un botón en la cabecera superior para salir limpiamente.

### v0.1 — Lanzamiento Inicial
- Herramienta de visualización de interfaces de red.
- Calculadora de subredes IP (compatible con ipcalc).
- Ping interactivo con salida coloreada en tiempo real.
- Traceroute asíncrono con soporte multiplataforma.
- Escáner LAN con ping sweep paralelo, resolución de hostname y consulta offline de fabricante MAC.
- Base de datos integrada de +52.000 prefijos OUI (IEEE).
- Interfaz TUI oscura con sidebar de navegación y atajos de teclado.

---

## 📝 Licencia

Proyecto privado. Todos los derechos reservados.

---

<p align="center">Hecho con ❤️  por Panoramix</p>
