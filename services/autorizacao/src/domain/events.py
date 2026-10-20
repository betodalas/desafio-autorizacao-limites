"""Eventos de domínio do contexto de Autorização (gravados na outbox e
eventualmente publicados como `TransacaoAutorizada` no EventBridge — ver
contracts/events/TransacaoAutorizada.v1.schema.json e ADR 02)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .value_objects import Money


@dataclass(frozen=True)
class TransacaoAutorizada:
    id_autorizacao: str
    id_contrato: str
    valor: Money
    saldo_reservado: Money
    correlation_id: str
    ocorrido_em: datetime
    trace_id: str | None = None

    @classmethod
    def agora(
        cls,
        id_autorizacao: str,
        id_contrato: str,
        valor: Money,
        saldo_reservado: Money,
        correlation_id: str,
        trace_id: str | None = None,
    ) -> "TransacaoAutorizada":
        return cls(
            id_autorizacao=id_autorizacao,
            id_contrato=id_contrato,
            valor=valor,
            saldo_reservado=saldo_reservado,
            correlation_id=correlation_id,
            ocorrido_em=datetime.now(timezone.utc),
            trace_id=trace_id,
        )
