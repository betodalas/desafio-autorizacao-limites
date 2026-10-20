"""Testes do caso de uso de processamento idempotente de
`TransacaoAutorizada`."""
import pytest

from src.application import ProcessarTransacaoAutorizadaUseCase
from src.domain import EventoInvalidoError
from src.infrastructure import InMemoryLancamentoRepository


def _envelope(event_id: str = "evt-1", valor: str = "150.00") -> dict:
    return {
        "event_id": event_id,
        "event_type": "TransacaoAutorizada",
        "event_version": "1.0",
        "occurred_at": "2026-02-10T13:45:02.123Z",
        "id_autorizacao": "d290f1ee-6c54-4b01-90e6-d701748f0851",
        "id_contrato": "CTR-998877",
        "valor": valor,
        "saldo_reservado": "4850.00",
        "correlation_id": "8f14e45f-ceea-467e-9eef-3a1f8a9c0b2e",
        "trace_id": None,
    }


def test_processa_evento_novo_criando_lancamento():
    uc = ProcessarTransacaoAutorizadaUseCase(InMemoryLancamentoRepository())

    lancamento, criado = uc.executar(_envelope())

    assert criado is True
    assert lancamento.event_id == "evt-1"
    assert str(lancamento.valor) == "150.00"


def test_reentrega_do_mesmo_event_id_e_idempotente():
    repo = InMemoryLancamentoRepository()
    uc = ProcessarTransacaoAutorizadaUseCase(repo)
    primeiro, _ = uc.executar(_envelope())

    segundo, criado = uc.executar(_envelope())

    assert criado is False
    assert segundo == primeiro
    assert len(repo.listar_por_contrato("CTR-998877")) == 1


def test_evento_sem_campos_obrigatorios_e_rejeitado():
    uc = ProcessarTransacaoAutorizadaUseCase(InMemoryLancamentoRepository())
    envelope = _envelope()
    del envelope["valor"]

    with pytest.raises(EventoInvalidoError):
        uc.executar(envelope)
