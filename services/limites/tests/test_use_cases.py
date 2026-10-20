"""Testes de integração dos casos de uso (application layer) com o
repositório in-memory (infrastructure layer) — validam a orquestração
completa sem qualquer dependência de AWS."""
import pytest

from src.application import (
    AplicarOperacaoComando,
    AplicarOperacaoLimiteUseCase,
    ConsultarSaldoLimiteUseCase,
)
from src.domain import ContratoNaoEncontradoError, LimiteInsuficienteError, Money
from src.domain.limite import Limite
from src.infrastructure import InMemoryLimiteRepository


@pytest.fixture
def repositorio():
    repo = InMemoryLimiteRepository()
    repo.adicionar(Limite(id_contrato="CTR-1", limite_total=Money.from_str("1000.00")))
    return repo


def test_aplicar_operacao_aprova_dentro_do_limite(repositorio):
    use_case = AplicarOperacaoLimiteUseCase(repositorio)

    evento = use_case.executar(
        AplicarOperacaoComando(
            id_contrato="CTR-1",
            id_autorizacao="AUTH-1",
            valor="150.00",
            tipo_operacao="DEBITO",
        )
    )

    assert evento.saldo_reservado == Money.from_str("150.00")

    consulta = ConsultarSaldoLimiteUseCase(repositorio).executar("CTR-1")
    assert consulta.saldo_reservado == Money.from_str("150.00")
    assert consulta.saldo_disponivel == Money.from_str("850.00")


def test_aplicar_operacao_recusa_limite_insuficiente(repositorio):
    use_case = AplicarOperacaoLimiteUseCase(repositorio)

    with pytest.raises(LimiteInsuficienteError):
        use_case.executar(
            AplicarOperacaoComando(
                id_contrato="CTR-1",
                id_autorizacao="AUTH-1",
                valor="1500.00",
                tipo_operacao="DEBITO",
            )
        )


def test_aplicar_operacao_contrato_inexistente(repositorio):
    use_case = AplicarOperacaoLimiteUseCase(repositorio)

    with pytest.raises(ContratoNaoEncontradoError):
        use_case.executar(
            AplicarOperacaoComando(
                id_contrato="CTR-INEXISTENTE",
                id_autorizacao="AUTH-1",
                valor="10.00",
                tipo_operacao="DEBITO",
            )
        )


def test_reenvio_com_mesma_id_autorizacao_e_idempotente(repositorio):
    use_case = AplicarOperacaoLimiteUseCase(repositorio)
    comando = AplicarOperacaoComando(
        id_contrato="CTR-1",
        id_autorizacao="AUTH-1",
        valor="150.00",
        tipo_operacao="DEBITO",
    )

    primeiro = use_case.executar(comando)
    segundo = use_case.executar(comando)

    assert primeiro == segundo
    consulta = ConsultarSaldoLimiteUseCase(repositorio).executar("CTR-1")
    assert consulta.saldo_reservado == Money.from_str("150.00")
