"""Caso de uso: sweeper de reconciliação (ver ADR 04).

Job periódico que resolve autorizações presas em PENDENTE há mais tempo
que o timeout configurado, consultando o Serviço de Limites como fonte de
verdade sobre se a reserva foi efetivada.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..domain import AutorizacaoRepository, LimiteGateway, StatusAutorizacao


@dataclass(frozen=True)
class ResultadoReconciliacao:
    total_verificadas: int
    total_aprovadas: int
    total_recusadas: int
    total_expiradas: int


class ReconciliarAutorizacoesPendentesUseCase:
    """Usa o próprio `LimiteGateway` (idempotente por `id_autorizacao`,
    ver ADR 03) para descobrir, de forma segura, se uma reserva pendente
    foi de fato efetivada do lado do Serviço de Limites."""

    def __init__(
        self,
        autorizacao_repository: AutorizacaoRepository,
        limite_gateway: LimiteGateway,
        timeout: timedelta = timedelta(seconds=30),
    ):
        self._autorizacoes = autorizacao_repository
        self._limite_gateway = limite_gateway
        self._timeout = timeout

    def executar(self, agora: datetime | None = None) -> ResultadoReconciliacao:
        agora = agora or datetime.now(timezone.utc)
        limite_tempo = agora - self._timeout
        pendentes = self._autorizacoes.listar_pendentes_antes_de(limite_tempo)

        aprovadas = recusadas = expiradas = 0
        for autorizacao in pendentes:
            consulta = self._limite_gateway.consultar_reserva(
                id_contrato=autorizacao.id_contrato,
                id_autorizacao=autorizacao.id_autorizacao,
            )
            if consulta is None:
                autorizacao.expirar()
                expiradas += 1
            else:
                autorizacao.aprovar(consulta.saldo_reservado)
                aprovadas += 1
            self._autorizacoes.salvar(autorizacao)

        return ResultadoReconciliacao(
            total_verificadas=len(pendentes),
            total_aprovadas=aprovadas,
            total_recusadas=recusadas,
            total_expiradas=expiradas,
        )
