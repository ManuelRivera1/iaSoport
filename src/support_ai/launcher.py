"""Keep the console alive after Ctrl+C so the local server can be restarted."""

import importlib
import signal
import sys

import uvicorn


def reload_application_modules():
    importlib.invalidate_caches()
    for name in list(sys.modules):
        if name.startswith("support_ai.") and name not in (__name__, "support_ai.launcher"):
            sys.modules.pop(name, None)


def main():
    # Uvicorn temporarily installs its shutdown handler and restores this handler.
    # Replaying Ctrl+C after shutdown must not terminate the restart menu.
    previous = signal.signal(signal.SIGINT, lambda *_: None)
    try:
        while True:
            try:
                uvicorn.run(
                    "support_ai.main:create_app", factory=True,
                    host="127.0.0.1", port=8000,
                )
            except KeyboardInterrupt:
                pass
            except (Exception, SystemExit) as exc:
                print(f"No se pudo mantener el servidor activo: {exc}")
            print("\nSupport AI detenido.\n[R] Reiniciar    [S] Salir")
            while True:
                try:
                    choice = input("Elige R o S: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    return
                if choice in ("s", "salir"):
                    return
                if choice in ("r", "reiniciar"):
                    print("\nReiniciando Support AI...\n")
                    reload_application_modules()
                    break
                print("Escribe R para reiniciar o S para salir.")
    finally:
        signal.signal(signal.SIGINT, previous)


if __name__ == "__main__":
    main()
