"""Adapter de `LimiteGateway` para uso local (sem AWS, sem HTTP), que
delega diretamente para o caso de uso do Serviço de Limites rodando no
mesmo processo.

Usado apenas pelo `make demo` local (ambos os serviços no mesmo
monorepo/processo) — em produção, o adapter real chama o Serviço de
Limites via HTTP através do API Gateway (ver ADR 01: cada serviço tem seu
próprio banco de dados e processo; aqui simulamos a chamada de rede).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from ..domain import LimiteGatewayIndeterminadoError, LimiteInsuficienteError
from ..domain.ports import LimiteGateway, LimiteGatewayResultado
from ..domain.value_objects import Money, TipoOperacao

_LIMITES_SRC = Path(__file__).resolve().parents[3] / "limites" / "src"
_SERVICES_DIR = _LIMITES_SRC.parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))


class InProcessLimiteGateway(LimiteGateway):
    def __init__(self, simular_falha_indeterminada: bool = False):
        from limites.src.application import (  # type: ignore import-untyped
            AplicarOperacaoComando,
            AplicarOperacaoLimiteUseCase,
        )
        from limites.src.domain import LimiteInsuficienteError as LimiteInsuficienteDoDominioDeLimites
        from limites.src.infrastructure import InMemoryLimiteRepository

        self._AplicarOperacaoComando = AplicarOperacaoComando
        self._LimiteInsuficienteDoDominioDeLimites = LimiteInsuficienteDoDominioDeLimites
        self._use_case = AplicarOperacaoLimiteUseCase(InMemoryLimiteRepository())
        self._repository = self._use_case._repository  # type: ignore[attr-defined]
        self._simular_falha_indeterminada = simular_falha_indeterminada

    def registrar_contrato(self, id_contrato: str, limite_total: str) -> None:
        from limites.src.domain import Limite
        from limites.src.domain import Money as MoneyDeLimites

        self._repository.adicionar(
            Limite(id_contrato=id_contrato, limite_total=MoneyDeLimites.from_str(limite_total))
        )

    def aplicar_operacao(
        self,
        id_contrato: str,
        id_autorizacao: str,
        valor: Money,
        tipo_operacao: TipoOperacao,
    ) -> LimiteGatewayResultado:
        if self._simular_falha_indeterminada:
            raise LimiteGatewayIndeterminadoError("Falha simulada de rede/timeout")
        try:
            evento = self._use_case.executar(
                self._AplicarOperacaoComando(
                    id_contrato=id_contrato,
                    id_autorizacao=id_autorizacao,
                    valor=str(valor),
                    tipo_operacao=tipo_operacao.value,
                )
            )
        except self._LimiteInsuficienteDoDominioDeLimites as exc:
            raise LimiteInsuficienteError(str(exc)) from exc
        return LimiteGatewayResultado(saldo_reservado=Money.from_str(str(evento.saldo_reservado)))

    def consultar_reserva(
        self, id_contrato: str, id_autorizacao: str
    ) -> Optional[LimiteGatewayResultado]:
        limite = self._repository.buscar_por_contrato(id_contrato)
        if limite is None or not limite.possui_reserva(id_autorizacao):
            return None
        reserva = limite.obter_reserva(id_autorizacao)
        return LimiteGatewayResultado(
            saldo_reservado=Money.from_str(str(reserva.evento.saldo_reservado))
        )
