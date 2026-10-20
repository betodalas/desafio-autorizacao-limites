"""Ports (interfaces) do worker de relay da outbox (ver ADR 02).

O relay é agnóstico ao bounded context de origem: qualquer serviço que
grave registros de outbox pode reutilizar este worker, desde que
implemente `OutboxSource` para seu próprio armazenamento.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol


class RegistroPendente(Protocol):
    """Estrutura mínima que um registro pendente de outbox precisa expor
    para o worker — compatível com `RegistroOutbox` do serviço de
    Autorização, mas não depende dele."""

    event_id: str
    tentativas: int

    def para_envelope(self) -> dict:
        ...


class OutboxSource(ABC):
    @abstractmethod
    def listar_pendentes(self, limite: int = 50) -> list[RegistroPendente]:
        ...

    @abstractmethod
    def marcar_publicado(self, event_id: str) -> None:
        ...

    @abstractmethod
    def marcar_falha(self, event_id: str, erro: str) -> None:
        ...


class EventPublisher(ABC):
    @abstractmethod
    def publicar(self, envelope: dict) -> None:
        """Publica o envelope do evento no destino (EventBridge em
        produção). Deve levantar exceção em caso de falha, para que o
        worker trate retry/backoff/DLQ."""
