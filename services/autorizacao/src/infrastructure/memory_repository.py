"""Adapters de persistência em memória — usados em testes e no `make demo`
local. Adapters DynamoDB reais ficam em `dynamodb_repository.py`."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..domain import Autorizacao, AutorizacaoRepository, IdempotenciaRepository, RegistroIdempotencia


class InMemoryAutorizacaoRepository(AutorizacaoRepository):
    def __init__(self) -> None:
        self._autorizacoes: dict[str, Autorizacao] = {}

    def buscar(self, id_autorizacao: str) -> Optional[Autorizacao]:
        return self._autorizacoes.get(id_autorizacao)

    def salvar(self, autorizacao: Autorizacao) -> None:
        self._autorizacoes[autorizacao.id_autorizacao] = autorizacao

    def listar_pendentes_antes_de(self, limite_tempo: datetime) -> list[Autorizacao]:
        from ..domain import StatusAutorizacao

        return [
            a
            for a in self._autorizacoes.values()
            if a.status == StatusAutorizacao.PENDENTE and a.criado_em < limite_tempo
        ]


class InMemoryIdempotenciaRepository(IdempotenciaRepository):
    def __init__(self) -> None:
        self._registros: dict[str, RegistroIdempotencia] = {}

    def buscar(self, idempotency_key: str) -> Optional[RegistroIdempotencia]:
        return self._registros.get(idempotency_key)

    def salvar(self, registro: RegistroIdempotencia) -> None:
        self._registros[registro.idempotency_key] = registro
