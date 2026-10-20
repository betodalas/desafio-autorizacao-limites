"""Test double de `LimiteGateway` — permite testar a saga de Autorização
de forma isolada (hexagonal), sem depender da implementação real do
Serviço de Limites (que já tem sua própria suíte de testes de domínio em
`services/limites/tests`)."""
from __future__ import annotations

from typing import Optional

from src.domain import LimiteGatewayIndeterminadoError, LimiteInsuficienteError, Money
from src.domain.ports import LimiteGateway, LimiteGatewayResultado
from src.domain.value_objects import TipoOperacao


class FakeLimiteGateway(LimiteGateway):
    """Comportamento controlável via atributos:

    - `recusar`: se True, toda chamada a `aplicar_operacao` levanta
      `LimiteInsuficienteError` (simula 402 do Serviço de Limites).
    - `indeterminado`: se True, toda chamada levanta
      `LimiteGatewayIndeterminadoError` (simula timeout/5xx).
    - `saldo_reservado_resultante`: valor devolvido em caso de sucesso.
    """

    def __init__(self) -> None:
        self.recusar = False
        self.indeterminado = False
        self.saldo_reservado_resultante = Money.from_str("150.00")
        self.chamadas: list[tuple[str, str, str, TipoOperacao]] = []
        self._reservas_efetivadas: dict[tuple[str, str], Money] = {}

    def aplicar_operacao(
        self,
        id_contrato: str,
        id_autorizacao: str,
        valor: Money,
        tipo_operacao: TipoOperacao,
    ) -> LimiteGatewayResultado:
        self.chamadas.append((id_contrato, id_autorizacao, str(valor), tipo_operacao))
        if self.indeterminado:
            raise LimiteGatewayIndeterminadoError("timeout simulado")
        if self.recusar:
            raise LimiteInsuficienteError("limite insuficiente simulado")
        self._reservas_efetivadas[(id_contrato, id_autorizacao)] = self.saldo_reservado_resultante
        return LimiteGatewayResultado(saldo_reservado=self.saldo_reservado_resultante)

    def consultar_reserva(
        self, id_contrato: str, id_autorizacao: str
    ) -> Optional[LimiteGatewayResultado]:
        saldo = self._reservas_efetivadas.get((id_contrato, id_autorizacao))
        if saldo is None:
            return None
        return LimiteGatewayResultado(saldo_reservado=saldo)
