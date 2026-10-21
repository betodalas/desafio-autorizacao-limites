"""Pequeno servidor HTTP (stdlib, sem dependências) que expõe a métrica
`pendentes` usada pelo KEDA `ScaledObject` do `outbox-relay`
(scaler `metrics-api`, ver deploy/k8s/outbox-relay.yaml).

Mantido deliberadamente fora do FastAPI para não acoplar o worker a uma
dependência web apenas para expor uma métrica simples.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from .ports import OutboxSource


def iniciar_servidor_metricas(
    source: OutboxSource, porta: int = 9090
) -> ThreadingHTTPServer:
    """Sobe um servidor HTTP em uma thread daemon e retorna o handle
    (chame `.shutdown()` para encerrar, ex. em testes)."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - assinatura exigida pela stdlib
            if self.path != "/metrics":
                self.send_response(404)
                self.end_headers()
                return
            pendentes = len(source.listar_pendentes(limite=1000))
            corpo = json.dumps({"pendentes": pendentes}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *args: object) -> None:  # silencia logs de acesso
            pass

    servidor = ThreadingHTTPServer(("0.0.0.0", porta), Handler)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    return servidor
