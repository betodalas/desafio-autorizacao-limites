"""Adapter de persistência em memória — usado em testes e para rodar o
serviço localmente sem AWS (ver Makefile `make demo`).

Não é thread-safe nem garante atomicidade transacional entre processos; em
produção, o adapter real é `dynamodb_repository.py`, que usa
`TransactWriteItems` (ADR 03).
"""
from __future__ import annotations

from typing import Optional

from ..domain import Limite, LimiteRepository


class InMemoryLimiteRepository(LimiteRepository):
    def __init__(self) -> None:
        self._limites: dict[str, Limite] = {}

    def buscar_por_contrato(self, id_contrato: str) -> Optional[Limite]:
        return self._limites.get(id_contrato)

    def salvar(self, limite: Limite) -> None:
        self._limites[limite.id_contrato] = limite

    def adicionar(self, limite: Limite) -> None:
        """Helper de teste/seed: registra um `Limite` já existente."""
        self._limites[limite.id_contrato] = limite
