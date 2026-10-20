"""Agregado raiz `Autorizacao`.

Representa a saga leve entre os contextos de Autorização e Limite (ver ADR
04): a autorização nasce `PENDENTE`, e só transiciona para `APROVADA` ou
`RECUSADA` depois que o resultado da reserva de limite é conhecido.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from .value_objects import Money, TipoOperacao


class StatusAutorizacao(str, Enum):
    PENDENTE = "PENDENTE"
    APROVADA = "APROVADA"
    RECUSADA = "RECUSADA"
    EXPIRADA = "EXPIRADA"


@dataclass
class Autorizacao:
    id_autorizacao: str
    id_contrato: str
    id_conta: str
    valor: Money
    moeda: str
    tipo_operacao: TipoOperacao
    status: StatusAutorizacao
    criado_em: datetime
    id_autorizacao_original: Optional[str] = None
    saldo_reservado: Optional[Money] = None

    @classmethod
    def nova_pendente(
        cls,
        id_autorizacao: str,
        id_contrato: str,
        id_conta: str,
        valor: Money,
        moeda: str,
        tipo_operacao: TipoOperacao,
        id_autorizacao_original: Optional[str] = None,
    ) -> "Autorizacao":
        valor.exige_positivo()
        return cls(
            id_autorizacao=id_autorizacao,
            id_contrato=id_contrato,
            id_conta=id_conta,
            valor=valor,
            moeda=moeda,
            tipo_operacao=tipo_operacao,
            status=StatusAutorizacao.PENDENTE,
            criado_em=datetime.now(timezone.utc),
            id_autorizacao_original=id_autorizacao_original,
        )

    def aprovar(self, saldo_reservado: Money) -> None:
        self.status = StatusAutorizacao.APROVADA
        self.saldo_reservado = saldo_reservado

    def recusar(self) -> None:
        self.status = StatusAutorizacao.RECUSADA

    def expirar(self) -> None:
        self.status = StatusAutorizacao.EXPIRADA

    @property
    def esta_pendente(self) -> bool:
        return self.status == StatusAutorizacao.PENDENTE
