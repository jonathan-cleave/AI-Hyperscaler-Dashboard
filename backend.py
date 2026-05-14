"""Local compatibility entry point for the Flask dashboard.

Render should still use: gunicorn ratio_dashboard.backend:app
"""

from __future__ import annotations

import os
import socket

from ratio_dashboard.backend import app


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def choose_port(start: int = 5000, attempts: int = 20) -> int:
    for port in range(start, start + attempts):
        if port_available(port):
            return port
    raise RuntimeError("No available local Flask port found.")


if __name__ == "__main__":
    port = int(os.environ["PORT"]) if os.environ.get("PORT") else choose_port()
    print(f"Dashboard running at http://127.0.0.1:{port}", flush=True)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
