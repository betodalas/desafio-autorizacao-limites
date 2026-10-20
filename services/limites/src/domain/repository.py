"""Port (interface) de persistência do agregado `Limite`.

O domínio depende apenas desta abstração (Dependency Inversion Principle);
adapters concretos (in-memory para testes, DynamoDB para produção) vivem em
`services/limites/src/infrastructure`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .limite import Limite


class LimiteRepository(ABC):
    @abstractmethod
    def buscar_por_contrato(self, id_contrato: str) -> Optional[Limite]:
        """Retorna o agregado `Limite` do contrato, ou `None` se não existir."""

    @abstractmethod
    def salvar(self, limite: Limite) -> None:
        """Persiste o estado atual do agregado.

        No adapter DynamoDB, esta operação é implementada com
        `TransactWriteItems` cobrindo: item do limite, item da reserva
        (idempotência) e registro de outbox — atomicamente (ver ADR 02 e
        ADR 03). O adapter in-memory usado em testes apenas guarda a
        referência do objeto.
        """
