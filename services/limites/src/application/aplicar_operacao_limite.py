"""Caso de uso: aplicar uma operação (DEBITO, CREDITO, RESERVA, ESTORNO)
sobre o limite de um contrato.

Camada de aplicação: orquestra o domínio e o port de persistência, sem
conter regra de negócio (que vive inteiramente em `domain`).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..domain import (
    ContratoNaoEncontradoError,
    LimiteOperacaoAplicada,
    LimiteRepository,
    Money,
    TipoOperacao,
)


@dataclass(frozen=True)
class AplicarOperacaoComando:
    id_contrato: str
    id_autorizacao: str
    valor: str
    tipo_operacao: str


class AplicarOperacaoLimiteUseCase:
    def __init__(self, repository: LimiteRepository):
        self._repository = repository

    def executar(self, comando: AplicarOperacaoComando) -> LimiteOperacaoAplicada:
        limite = self._repository.buscar_por_contrato(comando.id_contrato)
        if limite is None:
            raise ContratoNaoEncontradoError(
                f"Contrato {comando.id_contrato!r} não possui limite cadastrado"
            )

        valor = Money.from_str(comando.valor)
        tipo_operacao = TipoOperacao(comando.tipo_operacao)

        evento = limite.aplicar_operacao(
            id_autorizacao=comando.id_autorizacao,
            tipo_operacao=tipo_operacao,
            valor=valor,
        )

        self._repository.salvar(limite)
        return evento
