# 🗺️ NetKit Roadmap

Este documento define la hoja de ruta y las ideas futuras para la evolución de **NetKit**, organizadas en posibles futuras versiones o módulos.

## 🔜 Próximas Implementaciones (Backlog)

### 1. Escáner de Puertos (Port Scanner)
- **Descripción**: Herramienta para analizar puertos TCP (y opcionalmente UDP) abiertos en un dispositivo destino.
- **Características planeadas**:
  - Escaneo de puertos comunes (Top 100, Top 1000).
  - Escaneo de rangos personalizados (ej. `1-65535`).
  - Identificación básica de servicios por puerto conocido.
  - Ejecución asíncrona rápida utilizando concurrencia.

### 2. Gestor de Conexiones Remotas (Estilo MobaXterm)
- **Descripción**: Un módulo centralizado para almacenar y lanzar conexiones a dispositivos remotos de red.
- **Características planeadas**:
  - Almacenamiento seguro de perfiles de conexión (IP, usuario, puerto).
  - Lanzador integrado de sesiones **SSH** y **Telnet**.
  - (Opcional) Guardado de contraseñas de forma cifrada u organización por carpetas.

### 3. Herramienta SNMP / SNMPWALK
- **Descripción**: Módulo para interactuar con dispositivos de red a través del protocolo SNMP.
- **Características planeadas**:
  - Soporte para SNMP v1, v2c (y v3 en el futuro).
  - Funcionalidad de SNMP Get y Walk.
  - Árbol de navegación básico de OIDs comunes (ej. system, interfaces, routing).
  - Salida formateada y legible.

### 4. Mejoras Generales de la TUI
- **Descripción**: Evolución constante de la interfaz gráfica de terminal (Textual).
- **Características planeadas**:
  - Soporte para copiar al portapapeles resultados complejos desde la TUI.
  - Posibilidad de exportar resultados a un archivo de texto/JSON (ej. "Guardar escaneo LAN").
  - Menú de opciones de configuración (ej. timeout por defecto, puerto SSH por defecto).

---

## ✅ Historial de Versiones (Completadas)

### v0.1 - Lanzamiento Inicial
- [x] Visualización detallada de **Interfaces de red**.
- [x] **Calculadora de subredes** completa estilo ipcalc.
- [x] Herramienta **Ping** interactiva.
- [x] **Traceroute** asíncrono con salida coloreada.
- [x] **Escáner LAN** asíncrono con resolución MAC Vendor offline y hostname.
- [x] Estructura modular separando la interfaz (`tui`) de la lógica (`core`).
