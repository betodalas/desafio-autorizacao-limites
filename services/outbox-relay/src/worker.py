"""Worker de relay da outbox: lê registros pendentes, publica no destino
e trata retry/backoff/DLQ (ver ADR 02).

É propositalmente simples/síncrono (`run_once`) para ser fácil de testar
e de rodar tanto em loop (container local/k8s) quanto sob demanda em
testes. Produção escalaria via KEDA observando o tamanho da fila de
pendentes (ver ADR 05).
"""
from __future__ import annotations

import logging
import time

from .ports import EventPublisher, OutboxSource

logger = logging.getLogger("outbox_relay.worker")


class RelayWorker:
    def __init__(
        self,
        source: OutboxSource,
        publisher: EventPublisher,
        lote: int = 50,
        max_tentativas: int = 5,
    ):
        self._source = source
        self._publisher = publisher
        self._lote = lote
        self._max_tentativas = max_tentativas

    def run_once(self) -> int:
        """Processa um lote de pendentes. Retorna quantos foram
        publicados com sucesso nesta chamada."""
        pendentes = self._source.listar_pendentes(limite=self._lote)
        publicados = 0
        for registro in pendentes:
            try:
                self._publisher.publicar(registro.para_envelope())
                self._source.marcar_publicado(registro.event_id)
                publicados += 1
            except Exception as exc:  # noqa: BLE001 - qualquer falha de publicação é retry/DLQ
                logger.warning(
                    "falha ao publicar event_id=%s tentativa=%s: %s",
                    registro.event_id,
                    registro.tentativas + 1,
                    exc,
                )
                self._source.marcar_falha(registro.event_id, str(exc))
        return publicados

    def run_forever(self, intervalo_segundos: float = 2.0) -> None:  # pragma: no cover
        """Loop usado pelo entrypoint do container — não é exercitado em
        testes unitários (fluxo de infraestrutura/IO)."""
        while True:
            self.run_once()
            time.sleep(intervalo_segundos)
