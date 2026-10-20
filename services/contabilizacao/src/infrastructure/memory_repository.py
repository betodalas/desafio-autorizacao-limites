"""Adapter de persistência em memória — testes e `make demo` local."""
from __future__ import annotations

from typing import Optional

from ..domain import LancamentoContabil, LancamentoRepository


class InMemoryLancamentoRepository(LancamentoRepository):
    def __init__(self) -> None:
        self._por_event_id: dict[str, LancamentoContabil] = {}

    def buscar_por_event_id(self, event_id: str) -> Optional[LancamentoContabil]:
        return self._por_event_id.get(event_id)

    def salvar(self, lancamento: LancamentoContabil) -> None:
        self._por_event_id[lancamento.event_id] = lancamento

    def listar_por_contrato(self, id_contrato: str) -> list[LancamentoContabil]:
        return [l for l in self._por_event_id.values() if l.id_contrato == id_contrato]
