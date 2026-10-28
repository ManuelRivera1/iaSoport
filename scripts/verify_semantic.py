"""Offline acceptance check against the real model and configured local example."""

import socket
from unittest.mock import patch

from fastapi.testclient import TestClient

from support_ai.main import create_app

CASES = [
    ("¿Cómo consultar una orden?", "ms-orders.md"),
    ("¿Qué significa el error 504 en los pagos?", "ms-payment.md"),
    ("¿Cómo validar el archivo de conciliación SFTP?", "reconciliation.md"),
]


def offline_socket(*args, **kwargs):
    raise AssertionError("La verificación offline intentó abrir una conexión de red.")


def main() -> None:
    with TestClient(create_app(search_mode="semantic")) as client, patch.object(
        socket.socket, "connect", offline_socket,
    ), patch.object(socket.socket, "connect_ex", offline_socket):
        client.post("/api/v1/knowledge/sync").raise_for_status()
        prepared = client.post("/api/v1/knowledge/vectorize")
        prepared.raise_for_status()
        print("VECTORS", prepared.json())
        repeated = client.post("/api/v1/knowledge/vectorize")
        repeated.raise_for_status()
        assert repeated.json()["embeddings_created"] == 0
        print("REPEAT", repeated.json())
        for query, expected in CASES:
            response = client.post("/api/v1/search", json={"query": query, "top_k": 3})
            response.raise_for_status()
            data = response.json()
            paths = [hit["source"]["path"] for hit in data["hits"]]
            assert expected in paths, (expected, paths)
            assert not data["stale"]
            assert all(hit["source"]["commit"] == data["indexed_commit"] for hit in data["hits"])
            print("SEARCH", query, "->", paths)
        oversized = client.post("/api/v1/search", json={"query": "x " * 900})
        assert oversized.status_code == 503
        assert "límite de tokens" in oversized.json()["detail"]
        print("TOKEN_LIMIT", "rechazado sin truncamiento")


if __name__ == "__main__":
    main()
