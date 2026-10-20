"""Testes do `RelayWorker`: publicação com sucesso, retry com backoff
implícito (status permanece PENDENTE) e DLQ após esgotar tentativas."""
from src.worker import RelayWorker

from .fakes import FakeOutboxSource, FakePublisher, RegistroFake


def test_publica_registros_pendentes_e_marca_como_publicado():
    source = FakeOutboxSource([RegistroFake(event_id="e1", payload={"valor": "10.00"})])
    publisher = FakePublisher()
    worker = RelayWorker(source, publisher)

    publicados = worker.run_once()

    assert publicados == 1
    assert source._registros["e1"].status == "PUBLICADO"
    assert publisher.publicados == [{"valor": "10.00", "event_id": "e1"}]


def test_falha_de_publicacao_mantem_pendente_para_retry():
    source = FakeOutboxSource([RegistroFake(event_id="e1")])
    publisher = FakePublisher()
    publisher.falhar_para.add("e1")
    worker = RelayWorker(source, publisher)

    worker.run_once()

    registro = source._registros["e1"]
    assert registro.status == "PENDENTE"
    assert registro.tentativas == 1
    # Uma nova chamada deve tentar novamente o mesmo registro.
    assert worker._source.listar_pendentes() == [registro]


def test_falha_apos_max_tentativas_move_para_dlq():
    source = FakeOutboxSource([RegistroFake(event_id="e1")])
    source.max_tentativas = 2
    publisher = FakePublisher()
    publisher.falhar_para.add("e1")
    worker = RelayWorker(source, publisher)

    worker.run_once()
    worker.run_once()

    registro = source._registros["e1"]
    assert registro.tentativas == 2
    assert registro.status == "FALHA"
    assert source.listar_pendentes() == []
