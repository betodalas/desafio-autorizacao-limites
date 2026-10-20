"""Eventos de domínio do contexto de Limites.

Eventos são fatos imutáveis, nomeados no passado. São gravados na tabela de
outbox na mesma transação que o agregado (ver ADR 02), e eventualmente
publicados pelo outbox-relay. O schema externo (CloudEvents/EventBridge) é
responsabilidade da camada de infraestrutura — aqui modelamos apenas o fato
de negócio internamente ao contexto.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .value_objects import Money, TipoOperacao


@dataclass(frozen=True)
class LimiteOperacaoAplicada:
    """Fato: uma operação foi aplicada com sucesso ao limite de um contrato."""

    id_contrato: str
    id_autorizacao: str
    tipo_operacao: TipoOperacao
    valor: Money
    saldo_reservado: Money
    limite_total: Money
    ocorrido_em: datetime

    @classmethod
    def agora(
        cls,
        id_contrato: str,
        id_autorizacao: str,
        tipo_operacao: TipoOperacao,
        valor: Money,
        saldo_reservado: Money,
        limite_total: Money,
    ) -> "LimiteOperacaoAplicada":
        return cls(
            id_contrato=id_contrato,
            id_autorizacao=id_autorizacao,
            tipo_operacao=tipo_operacao,
            valor=valor,
            saldo_reservado=saldo_reservado,
            limite_total=limite_total,
            ocorrido_em=datetime.now(timezone.utc),
        )
