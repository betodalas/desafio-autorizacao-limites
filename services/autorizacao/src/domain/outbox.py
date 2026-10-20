"""Registro de Outbox do contexto de Autorização (ver ADR 02).

O agregado grava um `RegistroOutbox` na mesma "transação" lógica em que
persiste o resultado da autorização (em produção, ambos fariam parte do
mesmo `TransactWriteItems` contra a tabela de Autorizações + a tabela de
Outbox). O worker `outbox-relay` lê registros `PENDENTE`, publica no
EventBridge e marca como `PUBLICADO` — entrega é *at-least-once*, então
consumidores devem deduplicar por `event_id`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from .events import TransacaoAutorizada


class StatusOutbox(str, Enum):
    PENDENTE = "PENDENTE"
    PUBLICADO = "PUBLICADO"
    FALHA = "FALHA"


@dataclass
class RegistroOutbox:
    event_id: str
    event_type: str
    event_version: str
    evento: TransacaoAutorizada
    criado_em: datetime
    status: StatusOutbox = StatusOutbox.PENDENTE
    tentativas: int = 0
    ultimo_erro: Optional[str] = None

    @classmethod
    def para(cls, evento: TransacaoAutorizada, event_type: str = "TransacaoAutorizada") -> "RegistroOutbox":
        return cls(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            event_version="1.0",
            evento=evento,
            criado_em=datetime.now(timezone.utc),
        )

    def marcar_publicado(self) -> None:
        self.status = StatusOutbox.PUBLICADO

    def marcar_falha(self, erro: str, max_tentativas: int = 5) -> None:
        """Incrementa a contagem de tentativas. Enquanto não atingir
        `max_tentativas`, o registro permanece `PENDENTE` (continuará
        sendo retornado por `listar_pendentes` para nova tentativa, com
        backoff decidido pelo worker). Ao esgotar as tentativas, o status
        vira `FALHA` — terminal, equivalente a mover para uma DLQ."""
        self.tentativas += 1
        self.ultimo_erro = erro
        if self.tentativas >= max_tentativas:
            self.status = StatusOutbox.FALHA

    def para_envelope(self) -> dict:
        """Serializa no formato do contrato público do evento (ver
        contracts/events/TransacaoAutorizada.v1.schema.json)."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_version": self.event_version,
            "occurred_at": self.evento.ocorrido_em.isoformat(),
            "id_autorizacao": self.evento.id_autorizacao,
            "id_contrato": self.evento.id_contrato,
            "valor": str(self.evento.valor),
            "saldo_reservado": str(self.evento.saldo_reservado),
            "correlation_id": self.evento.correlation_id,
            "trace_id": self.evento.trace_id,
        }
