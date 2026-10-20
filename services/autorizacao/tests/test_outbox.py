"""Testa que a saga grava o evento `TransacaoAutorizada` na outbox apenas
quando a autorização é aprovada, e nunca quando é recusada/indeterminada."""
import pytest

from src.application import AutorizarTransacaoComando, AutorizarTransacaoUseCase
from src.domain import StatusOutbox
from src.infrastructure import (
    InMemoryAutorizacaoRepository,
    InMemoryIdempotenciaRepository,
    InMemoryOutboxRepository,
)

from .fakes import FakeLimiteGateway


def _comando(idempotency_key: str = "k1") -> AutorizarTransacaoComando:
    return AutorizarTransacaoComando(
        idempotency_key=idempotency_key,
        id_contrato="CTR-1",
        id_conta="000123",
        valor="150.00",
        moeda="BRL",
        tipo_operacao="DEBITO",
    )


def test_aprovacao_grava_evento_pendente_na_outbox():
    outbox = InMemoryOutboxRepository()
    uc = AutorizarTransacaoUseCase(
        InMemoryAutorizacaoRepository(), InMemoryIdempotenciaRepository(), FakeLimiteGateway(), outbox
    )

    resultado = uc.executar(_comando())

    pendentes = outbox.listar_pendentes()
    assert len(pendentes) == 1
    envelope = pendentes[0].para_envelope()
    assert envelope["event_type"] == "TransacaoAutorizada"
    assert envelope["id_autorizacao"] == resultado.id_autorizacao
    assert envelope["valor"] == "150.00"
    assert pendentes[0].status == StatusOutbox.PENDENTE


def test_recusa_nao_grava_evento_na_outbox():
    outbox = InMemoryOutboxRepository()
    gateway = FakeLimiteGateway()
    gateway.recusar = True
    uc = AutorizarTransacaoUseCase(
        InMemoryAutorizacaoRepository(), InMemoryIdempotenciaRepository(), gateway, outbox
    )

    with pytest.raises(Exception):
        uc.executar(_comando())

    assert outbox.listar_pendentes() == []
