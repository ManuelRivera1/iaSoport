"""A small terminal client; start the API before running this module."""

import httpx


def main() -> None:
    print("Support AI local. Escribe tu pregunta; /salir para terminar.")
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=240, trust_env=False) as client:
        while True:
            try:
                question = input("\nTú: ").strip()
                if question.lower() in ("/salir", "salir", "exit"):
                    break
                if not question:
                    continue
                response = client.post("/api/v1/chat", json={"question": question})
                data = response.json()
                if response.is_error:
                    print("Aviso:", data.get("detail", "No se pudo responder."))
                    continue
                print("\nSupport AI:", data["answer"])
                for i, source in enumerate(data["sources"], 1):
                    print(f"[{i}] {source['path']}:{source['start_line']}-{source['end_line']} "
                          f"commit {source['commit'][:12]}")
            except httpx.HTTPError:
                print("No se pudo conectar. Comprueba que FastAPI y Ollama estén activos.")
            except (EOFError, KeyboardInterrupt):
                print("\nHasta luego.")
                break


if __name__ == "__main__":
    main()
