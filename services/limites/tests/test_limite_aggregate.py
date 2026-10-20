"""Testes do agregado `Limite` — garantem a invariante central do domínio:
saldo_reservado + valor <= limite_total, além de idempotência por
`id_autorizacao` e comportamento de cada tipo de operação."""
import pytest

from src.domain import (
    LimiteInsuficienteError,
    Money,
    OperacaoInvalidaError,
    TipoOperacao,
    ValorInvalidoError,
)
from src.domain.limite import Limite


def novo_limite(limite_total="1000.00") -> Limite:
    return Limite(id_contrato="CTR-1", limite_total=Money.from_str(limite_total))


def test_debito_dentro_do_limite_e_aprovado():
    limite = novo_limite()

    evento = limite.aplicar_operacao("AUTH-1", TipoOperacao.DEBITO, Money.from_str("150.00"))

    assert limite.saldo_reservado == Money.from_str("150.00")
    assert evento.saldo_reservado == Money.from_str("150.00")
    assert evento.id_autorizacao == "AUTH-1"


def test_debito_que_excede_limite_e_recusado():
    limite = novo_limite(limite_total="100.00")

    with pytest.raises(LimiteInsuficienteError):
        limite.aplicar_operacao("AUTH-1", TipoOperacao.DEBITO, Money.from_str("150.00"))

    # nenhum efeito colateral deve ter sido aplicado
    assert limite.saldo_reservado == Money.zero()


def test_multiplos_debitos_acumulam_ate_estourar_limite():
    limite = novo_limite(limite_total="200.00")

    limite.aplicar_operacao("AUTH-1", TipoOperacao.DEBITO, Money.from_str("150.00"))

    with pytest.raises(LimiteInsuficienteError):
        limite.aplicar_operacao("AUTH-2", TipoOperacao.DEBITO, Money.from_str("100.00"))

    assert limite.saldo_reservado == Money.from_str("150.00")


def test_reserva_duplicada_e_idempotente():
    limite = novo_limite(limite_total="200.00")

    primeiro_evento = limite.aplicar_operacao(
        "AUTH-1", TipoOperacao.DEBITO, Money.from_str("150.00")
    )
    segundo_evento = limite.aplicar_operacao(
        "AUTH-1", TipoOperacao.DEBITO, Money.from_str("150.00")
    )

    assert primeiro_evento == segundo_evento
    # saldo não deve ter dobrado
    assert limite.saldo_reservado == Money.from_str("150.00")


def test_estorno_libera_saldo_reservado():
    limite = novo_limite(limite_total="200.00")
    limite.aplicar_operacao("AUTH-1", TipoOperacao.DEBITO, Money.from_str("150.00"))

    limite.aplicar_operacao("AUTH-1-ESTORNO", TipoOperacao.ESTORNO, Money.from_str("50.00"))

    assert limite.saldo_reservado == Money.from_str("100.00")


def test_estorno_maior_que_saldo_reservado_e_invalido():
    limite = novo_limite(limite_total="200.00")
    limite.aplicar_operacao("AUTH-1", TipoOperacao.DEBITO, Money.from_str("50.00"))

    with pytest.raises(OperacaoInvalidaError):
        limite.aplicar_operacao(
            "AUTH-1-ESTORNO", TipoOperacao.ESTORNO, Money.from_str("100.00")
        )


def test_credito_libera_saldo_como_estorno():
    limite = novo_limite(limite_total="200.00")
    limite.aplicar_operacao("AUTH-1", TipoOperacao.RESERVA, Money.from_str("150.00"))

    limite.aplicar_operacao("AUTH-2", TipoOperacao.CREDITO, Money.from_str("150.00"))

    assert limite.saldo_reservado == Money.zero()


def test_valor_zero_ou_negativo_e_invalido():
    limite = novo_limite()

    with pytest.raises(ValorInvalidoError):
        limite.aplicar_operacao("AUTH-1", TipoOperacao.DEBITO, Money.zero())
