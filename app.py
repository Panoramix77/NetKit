"""
NetKit — Panel de Control de Red
Punto de entrada principal de la aplicación.

Uso:
    python app.py
    python -m netkit          (cuando esté empaquetado)
"""
from tui.interfaz import NetKitApp


def main() -> None:
    """Arranca la TUI de NetKit."""
    app = NetKitApp()
    app.run()


if __name__ == "__main__":
    main()
