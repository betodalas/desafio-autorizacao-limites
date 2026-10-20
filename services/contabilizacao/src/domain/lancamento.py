"""Agregado `LancamentoContabil` — o fato contábil derivado de um evento
`TransacaoAutorizada` consumido do EventBridge/SQS (ver contracts/events).

Cada lançamento é identificado pelo `event_id` do evento de origem, que é
a chave de deduplicação: a entrega é *at-least-once* (ADR 02), então o
mesmo evento pode chegar mais de uma vez — o agregado é construído apenas
uma vez por `event_id` (ver `ProcessarTransacaoAutorizadaUseCase`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .value_objects import Money


@dataclass(frozen=True)
class LancamentoContabil:
    event_id: str
    id_autorizacao: str
    id_contrato: str
    valor: Money
    saldo_reservado: Money
    ocorrido_em: datetime
    processado_em: datetime
