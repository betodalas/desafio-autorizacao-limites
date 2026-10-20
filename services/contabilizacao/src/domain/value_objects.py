"""Value object monetário do contexto de Contabilização.

Duplicado deliberadamente (não compartilhado) em relação aos demais
bounded contexts — ver rationale em `services/autorizacao/src/domain/value_objects.py`
e ADR 01.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


class ValorInvalidoError(Exception):
    """Valor monetário inválido (negativo, não numérico, etc.)."""


@dataclass(frozen=True)
class Money:
    valor: Decimal

    def __post_init__(self) -> None:
        quantizado = self.valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        object.__setattr__(self, "valor", quantizado)

    @classmethod
    def from_str(cls, texto: str) -> "Money":
        try:
            return cls(Decimal(texto))
        except Exception as exc:  # noqa: BLE001 - normalizamos qualquer erro de parsing
            raise ValorInvalidoError(f"Valor monetário inválido: {texto!r}") from exc

    @classmethod
    def zero(cls) -> "Money":
        return cls(Decimal("0.00"))

    def __add__(self, outro: "Money") -> "Money":
        return Money(self.valor + outro.valor)

    def __sub__(self, outro: "Money") -> "Money":
        return Money(self.valor - outro.valor)

    def __str__(self) -> str:
        return f"{self.valor:.2f}"
