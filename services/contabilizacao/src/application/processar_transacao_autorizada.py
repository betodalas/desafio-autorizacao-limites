"""Caso de uso: processar um evento `TransacaoAutorizada` consumido do
EventBridge/SQS e materializar um lançamento contábil, de forma
idempotente por `event_id` (consumidor *at-least-once*, ver ADR 02)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..domain import EventoInvalidoError, LancamentoContabil, LancamentoRepository, Money

_CAMPOS_OBRIGATORIOS = (
    "event_id",
    "event_type",
    "occurred_at",
    "id_autorizacao",
    "id_contrato",
    "valor",
    "saldo_reservado",
)


class ProcessarTransacaoAutorizadaUseCase:
    def __init__(self, repository: LancamentoRepository):
        self._repository = repository

    def executar(self, envelope: dict[str, Any]) -> tuple[LancamentoContabil, bool]:
        """Retorna `(lancamento, criado)`: `criado=False` quando o evento
        já havia sido processado anteriormente (reentrega idempotente)."""
        faltantes = [campo for campo in _CAMPOS_OBRIGATORIOS if not envelope.get(campo)]
        if faltantes:
            raise EventoInvalidoError(f"Campos obrigatórios ausentes no evento: {faltantes}")

        existente = self._repository.buscar_por_event_id(envelope["event_id"])
        if existente is not None:
            return existente, False

        lancamento = LancamentoContabil(
            event_id=envelope["event_id"],
            id_autorizacao=envelope["id_autorizacao"],
            id_contrato=envelope["id_contrato"],
            valor=Money.from_str(envelope["valor"]),
            saldo_reservado=Money.from_str(envelope["saldo_reservado"]),
            ocorrido_em=datetime.fromisoformat(envelope["occurred_at"].replace("Z", "+00:00")),
            processado_em=datetime.now(timezone.utc),
        )
        self._repository.salvar(lancamento)
        return lancamento, True
