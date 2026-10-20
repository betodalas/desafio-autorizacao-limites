"""Testes do value object Money."""
import pytest

from src.domain import Money, ValorInvalidoError


def test_money_arredonda_para_duas_casas():
    assert str(Money.from_str("150")) == "150.00"
    assert str(Money.from_str("10.005")) == "10.01"  # ROUND_HALF_UP


def test_money_rejeita_negativo():
    with pytest.raises(ValorInvalidoError):
        Money.from_str("-1.00")


def test_money_rejeita_formato_invalido():
    with pytest.raises(ValorInvalidoError):
        Money.from_str("abc")


def test_money_exige_positivo():
    with pytest.raises(ValorInvalidoError):
        Money.zero().exige_positivo()


def test_money_comparacoes_e_aritmetica():
    cem = Money.from_str("100.00")
    cinquenta = Money.from_str("50.00")
    assert cinquenta < cem
    assert cem > cinquenta
    assert (cem - cinquenta) == Money.from_str("50.00")
    assert (cem + cinquenta) == Money.from_str("150.00")
