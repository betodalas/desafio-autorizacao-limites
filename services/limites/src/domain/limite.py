"""Agregado raiz `Limite` do contexto de Limites.

Invariante central: saldo_reservado + valor <= limite_total, garantida
aqui no domínio (para testes e uso em memória) e reforçada atomicamente na
infraestrutura via DynamoDB TransactWriteItems (ver ADR 03) para proteger
contra concorrência real entre processos.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .events import LimiteOperacaoAplicada
from .exceptions import ContratoNaoEncontradoError
from .politicas import politica_para
from .value_objects import Money, TipoOperacao


@dataclass(frozen=True)
class Reserva:
    """Entidade filha: representa o efeito de uma operação aplicada ao
    limite, identificada por `id_autorizacao` para garantir idempotência —
    reaplicar a mesma `id_autorizacao` é um no-op que retorna o evento
    originalmente gerado, em vez de aplicar o efeito duas vezes."""

    id_autorizacao: str
    tipo_operacao: TipoOperacao
    valor: Money
    evento: LimiteOperacaoAplicada


class Limite:
    """Agregado raiz. Encapsula o saldo reservado e todas as reservas
    (idempotentes por `id_autorizacao`) associadas a um contrato."""

    def __init__(self, id_contrato: str, limite_total: Money):
        if not id_contrato:
            raise ContratoNaoEncontradoError("id_contrato não pode ser vazio")
        self.id_contrato = id_contrato
        self.limite_total = limite_total
        self._reservas: dict[str, Reserva] = {}
        self._saldo_reservado: Money = Money.zero()

    @property
    def saldo_reservado(self) -> Money:
        return self._saldo_reservado

    def possui_reserva(self, id_autorizacao: str) -> bool:
        return id_autorizacao in self._reservas

    def obter_reserva(self, id_autorizacao: str) -> Reserva:
        return self._reservas[id_autorizacao]

    def aplicar_operacao(
        self,
        id_autorizacao: str,
        tipo_operacao: TipoOperacao,
        valor: Money,
    ) -> LimiteOperacaoAplicada:
        """Aplica uma operação ao limite, retornando o evento de domínio
        resultante.

        Idempotente: se `id_autorizacao` já foi aplicada anteriormente,
        retorna o evento original sem reaplicar o efeito — espelha a
        garantia de `attribute_not_exists(id_autorizacao)` do adapter
        DynamoDB (ADR 03), permitindo testar a idempotência sem AWS.
        """
        valor.exige_positivo()

        reserva_existente = self._reservas.get(id_autorizacao)
        if reserva_existente is not None:
            return reserva_existente.evento

        politica = politica_para(tipo_operacao, self.limite_total)
        novo_saldo = politica.novo_saldo(self._saldo_reservado, valor)

        evento = LimiteOperacaoAplicada.agora(
            id_contrato=self.id_contrato,
            id_autorizacao=id_autorizacao,
            tipo_operacao=tipo_operacao,
            valor=valor,
            saldo_reservado=novo_saldo,
            limite_total=self.limite_total,
        )

        self._saldo_reservado = novo_saldo
        self._reservas[id_autorizacao] = Reserva(
            id_autorizacao=id_autorizacao,
            tipo_operacao=tipo_operacao,
            valor=valor,
            evento=evento,
        )
        return evento

