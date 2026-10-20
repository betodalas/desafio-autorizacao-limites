"""Port de persistência dos lançamentos contábeis."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .lancamento import LancamentoContabil


class LancamentoRepository(ABC):
    @abstractmethod
    def buscar_por_event_id(self, event_id: str) -> Optional[LancamentoContabil]:
        """Usado para deduplicar entrega at-least-once (ver ADR 02): se já
        existe um lançamento para este `event_id`, o consumidor deve
        ignorar o reprocessamento sem criar um lançamento duplicado."""

    @abstractmethod
    def salvar(self, lancamento: LancamentoContabil) -> None:
        ...

    @abstractmethod
    def listar_por_contrato(self, id_contrato: str) -> list[LancamentoContabil]:
        ...
