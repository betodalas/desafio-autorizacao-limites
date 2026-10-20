"""Caso de uso: consultar o saldo de limite disponível de um contrato."""
from __future__ import annotations

from dataclasses import dataclass

from ..domain import ContratoNaoEncontradoError, LimiteRepository, Money


@dataclass(frozen=True)
class SaldoLimiteConsulta:
    id_contrato: str
    limite_total: Money
    saldo_reservado: Money
    saldo_disponivel: Money


class ConsultarSaldoLimiteUseCase:
    def __init__(self, repository: LimiteRepository):
        self._repository = repository

    def executar(self, id_contrato: str) -> SaldoLimiteConsulta:
        limite = self._repository.buscar_por_contrato(id_contrato)
        if limite is None:
            raise ContratoNaoEncontradoError(
                f"Contrato {id_contrato!r} não possui limite cadastrado"
            )
        return SaldoLimiteConsulta(
            id_contrato=limite.id_contrato,
            limite_total=limite.limite_total,
            saldo_reservado=limite.saldo_reservado,
            saldo_disponivel=limite.limite_total - limite.saldo_reservado,
        )
