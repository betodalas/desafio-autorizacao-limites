"""Testes da saga de autorização: aprovação, recusa (402), concorrência de
idempotência (409), payload divergente (422) e reenvio idempotente (200)."""
import pytest

from src.application import AutorizacaoResultado, AutorizarTransacaoComando, AutorizarTransacaoUseCase
from src.domain import LimiteInsuficienteError, OperacaoEmAndamentoError, PayloadDivergenteError
from src.infrastructure import InMemoryAutorizacaoRepository, InMemoryIdempotenciaRepository

from .fakes import FakeLimiteGateway


def novo_comando(**overrides) -> AutorizarTransacaoComando:
    base = dict(
        idempotency_key="11111111-1111-1111-1111-111111111111",
        id_contrato="CTR-1",
        id_conta="00012345678",
        valor="150.00",
        moeda="BRL",
        tipo_operacao="DEBITO",
    )
    base.update(overrides)
    return AutorizarTransacaoComando(**base)


@pytest.fixture
def ambiente():
    autorizacoes = InMemoryAutorizacaoRepository()
    idempotencias = InMemoryIdempotenciaRepository()
    gateway = FakeLimiteGateway()
    use_case = AutorizarTransacaoUseCase(autorizacoes, idempotencias, gateway)
    return use_case, autorizacoes, idempotencias, gateway


def test_autorizacao_aprovada(ambiente):
    use_case, _, _, gateway = ambiente

    resultado = use_case.executar(novo_comando())

    assert resultado.status == "APROVADA"
    assert resultado.saldo_reservado == "150.00"
    assert resultado.repetida is False
    assert len(gateway.chamadas) == 1


def test_autorizacao_recusada_por_limite_insuficiente(ambiente):
    use_case, _, _, gateway = ambiente
    gateway.recusar = True

    with pytest.raises(LimiteInsuficienteError):
        use_case.executar(novo_comando())


def test_reenvio_com_mesmo_payload_e_idempotente(ambiente):
    use_case, _, _, _ = ambiente
    comando = novo_comando()

    primeiro = use_case.executar(comando)
    segundo = use_case.executar(comando)

    assert primeiro.id_autorizacao == segundo.id_autorizacao
    assert segundo.repetida is True


def test_reenvio_de_autorizacao_recusada_mantem_a_recusa(ambiente):
    use_case, _, _, gateway = ambiente
    gateway.recusar = True
    comando = novo_comando()

    with pytest.raises(LimiteInsuficienteError):
        use_case.executar(comando)
    # reenvio deve continuar recusando (decisão idempotente), sem rechamar o gateway
    with pytest.raises(LimiteInsuficienteError):
        use_case.executar(comando)
    assert len(gateway.chamadas) == 1


def test_reenvio_com_payload_diferente_e_invalido(ambiente):
    use_case, _, _, _ = ambiente
    use_case.executar(novo_comando())

    with pytest.raises(PayloadDivergenteError):
        use_case.executar(novo_comando(valor="999.00"))


def test_falha_indeterminada_do_gateway_mantem_pendente_e_retorna_409(ambiente):
    use_case, autorizacoes, idempotencias, gateway = ambiente
    gateway.indeterminado = True
    comando = novo_comando()

    with pytest.raises(OperacaoEmAndamentoError):
        use_case.executar(comando)

    # autorização permanece PENDENTE; reenvio também deve retornar 409
    # (ainda em andamento), nunca duplicando a tentativa automaticamente
    with pytest.raises(OperacaoEmAndamentoError):
        use_case.executar(comando)
