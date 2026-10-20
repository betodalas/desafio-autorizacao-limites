"""Value objects do domínio de Limites.

Value objects são imutáveis e definem igualdade por valor (não identidade).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from enum import Enum


class TipoOperacao(str, Enum):
    """Tipos de operação suportados, conforme contrato de API.

    Cada tipo tem uma política própria de impacto sobre o saldo reservado
    do limite (ver `services/limites/src/domain/politicas.py`).
    """

    DEBITO = "DEBITO"
    CREDITO = "CREDITO"
    RESERVA = "RESERVA"
    ESTORNO = "ESTORNO"


class ValorInvalidoError(ValueError):
    """Levantado quando um valor monetário não pode ser representado como
    Money (formato inválido ou fora da faixa permitida)."""


@dataclass(frozen=True)
class Money:
    """Representa um valor monetário com exatamente duas casas decimais.

    Usamos `Decimal` (nunca `float`) para evitar erros de arredondamento em
    cálculos financeiros. Na borda (API/eventos), valores são transportados
    como string (ex: "150.00") e convertidos via `Money.from_str`.
    """

    valor: Decimal

    def __post_init__(self) -> None:
        quantizado = self.valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        object.__setattr__(self, "valor", quantizado)
        if self.valor < Decimal("0"):
            raise ValorInvalidoError("Valor monetário não pode ser negativo")

    @classmethod
    def from_str(cls, valor_str: str) -> "Money":
        try:
            return cls(Decimal(valor_str))
        except (InvalidOperation, TypeError) as exc:
            raise ValorInvalidoError(
                f"Valor monetário inválido: {valor_str!r}"
            ) from exc

    @classmethod
    def zero(cls) -> "Money":
        return cls(Decimal("0"))

    def exige_positivo(self) -> "Money":
        """Valida que o valor é estritamente maior que zero (ex: valor de
        uma transação não pode ser zero ou negativo)."""
        if self.valor <= Decimal("0"):
            raise ValorInvalidoError("Valor monetário deve ser maior que zero")
        return self

    def __add__(self, outro: "Money") -> "Money":
        return Money(self.valor + outro.valor)

    def __sub__(self, outro: "Money") -> "Money":
        return Money(self.valor - outro.valor)

    def __le__(self, outro: "Money") -> bool:
        return self.valor <= outro.valor

    def __lt__(self, outro: "Money") -> bool:
        return self.valor < outro.valor

    def __ge__(self, outro: "Money") -> bool:
        return self.valor >= outro.valor

    def __gt__(self, outro: "Money") -> bool:
        return self.valor > outro.valor

    def __str__(self) -> str:
        return f"{self.valor:.2f}"
