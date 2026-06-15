# Contexto de Desarrollo: Panel de Control de Red (TUI Multiplataforma)

Este documento sirve como guía de contexto, arquitectura y restricciones para los agentes de IA que colaboren en el desarrollo de este proyecto. El objetivo es construir una herramienta de gestión de redes interactiva mediante una interfaz de terminal (TUI) eficiente, modular y totalmente multiplataforma (Windows y Linux).

---

## 🎯 Objetivos del Proyecto
1. **Interfaz Visual Interactiva (TUI):** Actuar como orquestador central o "dashboard" dinámico para ejecutar herramientas de red.
2. **Modularidad Completa:** Separar radicalmente la interfaz de usuario de la lógica de red (Core).
3. **Portabilidad "Doble Clic":** Diseñar el código pensando en un empaquetado final simple y eficiente para el usuario final sin dependencias externas.

---

## 📂 Esquema de Organización del Proyecto

El proyecto debe mantener estrictamente la siguiente estructura de directorios para garantizar el desacoplamiento:

```text
mi_herramienta_red/
├── app.py             # Punto de entrada principal (Arranca la TUI)
├── requirements.txt   # Dependencias del proyecto (Fijar versiones)
├── agents.md          # Este archivo de contexto para IA
├── tui/
│   ├── __init__.py
│   └── interfaz.py    # Capa visual, menús, botones, formularios y eventos (Textual)
└── core/
    ├── __init__.py
    └── red.py         # Capa de lógica: funciones puras de red escritas desde cero
