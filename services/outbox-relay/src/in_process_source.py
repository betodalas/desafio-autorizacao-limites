"""Adapter de `OutboxSource` para uso local (`make demo`), que delega
para o `InMemoryOutboxRepository` do serviço de Autorização rodando no
mesmo processo — mesma técnica de `services/autorizacao/.../limite_gateway_in_process.py`.

Em produção, cada serviço produtor de eventos tem sua própria tabela de
outbox no DynamoDB, e o relay seria configurado (via env var) para ler da
tabela correspondente a uma única origem por deployment."""
from __future__ import annotations

import sys
from pathlib import Path

from .ports import OutboxSource

_SERVICES_DIR = Path(__file__).resolve().parents[2]
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))


class InProcessAutorizacaoOutboxSource(OutboxSource):
    """Lê diretamente de uma instância de
    `autorizacao.src.infrastructure.InMemoryOutboxRepository` compartilhada
    com o processo do serviço de Autorização."""

    def __init__(self, outbox_repository) -> None:  # type: ignore[no-untyped-def]
        self._repository = outbox_repository

    def listar_pendentes(self, limite: int = 50):
        return self._repository.listar_pendentes(limite=limite)

    def marcar_publicado(self, event_id: str) -> None:
        registro = self._repository._registros[event_id]  # acesso direto: adapter local de demo
        registro.marcar_publicado()

    def marcar_falha(self, event_id: str, erro: str) -> None:
        registro = self._repository._registros[event_id]
        registro.marcar_falha(erro)
