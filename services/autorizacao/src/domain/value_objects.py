"""Value objects do contexto de Autorização.

Deliberadamente duplicados (não compartilhados via biblioteca comum) em
relação aos de `services/limites/src/domain/value_objects.py`: cada
bounded context define sua própria linguagem ubíqua e evolui de forma
independente (ver ADR 01). O acoplamento por biblioteca compartilhada de
domínio é um anti-padrão comum em "falsos microsserviços".
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from enum import Enum


class TipoOperacao(str, Enum):
    DEBITO = "DEBITO"
    CREDITO = "CREDITO"
    RESERVA = "RESERVA"
    ESTORNO = "ESTORNO"


class ValorInvalidoError(ValueError):
    pass


@dataclass(frozen=True)
class Money:
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
            raise ValorInvalidoError(f"Valor monetário inválido: {valor_str!r}") from exc

    def exige_positivo(self) -> "Money":
        if self.valor <= Decimal("0"):
            raise ValorInvalidoError("Valor monetário deve ser maior que zero")
        return self

    def __str__(self) -> str:
        return f"{self.valor:.2f}"
