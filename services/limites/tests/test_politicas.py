"""Testes das políticas por tipo de operação (Strategy/OCP)."""
import pytest

from src.domain import LimiteInsuficienteError, Money, OperacaoInvalidaError, TipoOperacao
from src.domain.exceptions import TipoOperacaoDesconhecidoError
from src.domain.politicas import politica_para


def test_politica_consumo_respeita_teto():
    politica = politica_para(TipoOperacao.DEBITO, Money.from_str("100.00"))
    novo_saldo = politica.novo_saldo(Money.from_str("50.00"), Money.from_str("50.00"))
    assert novo_saldo == Money.from_str("100.00")


def test_politica_consumo_recusa_estouro():
    politica = politica_para(TipoOperacao.RESERVA, Money.from_str("100.00"))
    with pytest.raises(LimiteInsuficienteError):
        politica.novo_saldo(Money.from_str("50.00"), Money.from_str("50.01"))


def test_politica_liberacao_nao_permite_saldo_negativo():
    politica = politica_para(TipoOperacao.ESTORNO, Money.from_str("100.00"))
    with pytest.raises(OperacaoInvalidaError):
        politica.novo_saldo(Money.from_str("30.00"), Money.from_str("50.00"))


def test_politica_para_tipo_desconhecido_levanta_erro():
    with pytest.raises(TipoOperacaoDesconhecidoError):
        politica_para("INVALIDO", Money.from_str("100.00"))  # type: ignore[arg-type]
