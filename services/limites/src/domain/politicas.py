"""Políticas de operação sobre o saldo reservado do limite.

Aplica o princípio Open/Closed (SOLID): para suportar um novo
`tipo_operacao`, basta implementar `PoliticaOperacao` e registrá-la em
`POLITICAS_POR_TIPO`, sem alterar o agregado `Limite` nem as políticas
existentes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .exceptions import LimiteInsuficienteError, OperacaoInvalidaError
from .value_objects import Money, TipoOperacao


class PoliticaOperacao(ABC):
    """Define como um tipo de operação afeta o saldo reservado do limite e
    qual invariante deve ser validada."""

    @abstractmethod
    def novo_saldo(self, saldo_atual: Money, valor: Money) -> Money:
        """Calcula o novo saldo reservado após aplicar a operação,
        levantando a exceção de domínio apropriada se a invariante for
        violada."""


class PoliticaConsumoDeLimite(PoliticaOperacao):
    """Usada por DEBITO e RESERVA: a operação consome limite disponível.

    Invariante: saldo_reservado + valor <= limite_total
    """

    def __init__(self, limite_total: Money):
        self._limite_total = limite_total

    def novo_saldo(self, saldo_atual: Money, valor: Money) -> Money:
        novo_saldo = saldo_atual + valor
        if novo_saldo > self._limite_total:
            raise LimiteInsuficienteError(
                f"Saldo reservado resultante ({novo_saldo}) excederia o "
                f"limite total ({self._limite_total})"
            )
        return novo_saldo


class PoliticaLiberacaoDeLimite(PoliticaOperacao):
    """Usada por CREDITO e ESTORNO: a operação libera limite previamente
    reservado.

    Invariante: saldo_reservado - valor >= 0
    """

    def novo_saldo(self, saldo_atual: Money, valor: Money) -> Money:
        if valor > saldo_atual:
            raise OperacaoInvalidaError(
                f"Valor a liberar ({valor}) é maior que o saldo reservado "
                f"atual ({saldo_atual})"
            )
        return saldo_atual - valor


def politica_para(tipo_operacao: TipoOperacao, limite_total: Money) -> PoliticaOperacao:
    """Factory que seleciona a política de acordo com o tipo de operação."""

    mapa: dict[TipoOperacao, PoliticaOperacao] = {
        TipoOperacao.DEBITO: PoliticaConsumoDeLimite(limite_total),
        TipoOperacao.RESERVA: PoliticaConsumoDeLimite(limite_total),
        TipoOperacao.CREDITO: PoliticaLiberacaoDeLimite(),
        TipoOperacao.ESTORNO: PoliticaLiberacaoDeLimite(),
    }
    try:
        return mapa[tipo_operacao]
    except KeyError as exc:
        from .exceptions import TipoOperacaoDesconhecidoError

        raise TipoOperacaoDesconhecidoError(
            f"Nenhuma política registrada para tipo_operacao={tipo_operacao!r}"
        ) from exc
