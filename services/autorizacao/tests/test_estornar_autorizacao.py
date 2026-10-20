"""Testes do fluxo de estorno de uma autorização aprovada."""
import pytest

from src.application import (
    AutorizarTransacaoComando,
    AutorizarTransacaoUseCase,
    EstornarAutorizacaoComando,
    EstornarAutorizacaoUseCase,
)
from src.domain import AutorizacaoOriginalInvalidaError, LimiteOperacaoInvalidaError
from src.infrastructure import InMemoryAutorizacaoRepository, InMemoryIdempotenciaRepository

from .fakes import FakeLimiteGateway


@pytest.fixture
def ambiente():
    autorizacoes = InMemoryAutorizacaoRepository()
    idempotencias = InMemoryIdempotenciaRepository()
    gateway = FakeLimiteGateway()
    autorizar = AutorizarTransacaoUseCase(autorizacoes, idempotencias, gateway)
    estornar = EstornarAutorizacaoUseCase(autorizacoes, idempotencias, gateway)
    return autorizar, estornar, gateway


def test_estorno_de_autorizacao_aprovada(ambiente):
    autorizar, estornar, _ = ambiente
    original = autorizar.executar(
        AutorizarTransacaoComando(
            idempotency_key="k1",
            id_contrato="CTR-1",
            id_conta="000123",
            valor="150.00",
            moeda="BRL",
            tipo_operacao="DEBITO",
        )
    )

    resultado = estornar.executar(
        EstornarAutorizacaoComando(
            idempotency_key="k2",
            id_contrato="CTR-1",
            id_autorizacao_original=original.id_autorizacao,
            valor="150.00",
            moeda="BRL",
        )
    )

    assert resultado.status == "APROVADA"


def test_estorno_de_autorizacao_inexistente_e_invalido(ambiente):
    _, estornar, _ = ambiente

    with pytest.raises(AutorizacaoOriginalInvalidaError):
        estornar.executar(
            EstornarAutorizacaoComando(
                idempotency_key="k2",
                id_contrato="CTR-1",
                id_autorizacao_original="00000000-0000-0000-0000-000000000000",
                valor="10.00",
                moeda="BRL",
            )
        )


def test_estorno_maior_que_reservado_e_recusado(ambiente):
    autorizar, estornar, gateway = ambiente
    original = autorizar.executar(
        AutorizarTransacaoComando(
            idempotency_key="k1",
            id_contrato="CTR-1",
            id_conta="000123",
            valor="150.00",
            moeda="BRL",
            tipo_operacao="DEBITO",
        )
    )
    gateway.operacao_invalida = True

    with pytest.raises(LimiteOperacaoInvalidaError):
        estornar.executar(
            EstornarAutorizacaoComando(
                idempotency_key="k2",
                id_contrato="CTR-1",
                id_autorizacao_original=original.id_autorizacao,
                valor="150.00",
                moeda="BRL",
            )
        )
