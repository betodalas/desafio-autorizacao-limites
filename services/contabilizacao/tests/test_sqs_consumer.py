"""Testes do desembrulhamento de mensagens SQS alimentadas pelo
EventBridge: o corpo da mensagem é o envelope do EventBridge
(`source`/`detail-type`/`detail`), não o payload de negócio puro."""
from src.infrastructure import extrair_detail


def test_extrai_detail_de_envelope_eventbridge():
    payload_negocio = {"event_id": "evt-1", "valor": "150.00"}
    body_eventbridge = {
        "version": "0",
        "id": "94bc22c6-1adc-4aca-a8ae-d7f250efb3fe",
        "detail-type": "TransacaoAutorizada",
        "source": "autorizacao",
        "account": "000000000000",
        "time": "2026-10-22T13:12:23Z",
        "region": "us-east-1",
        "resources": [],
        "detail": payload_negocio,
    }

    assert extrair_detail(body_eventbridge) == payload_negocio


def test_mantem_payload_quando_ja_eh_o_detail_puro():
    """Compatibilidade com publicação direta na fila (sem passar pelo
    EventBridge), usada em testes/smoke manual."""
    payload_negocio = {"event_id": "evt-1", "valor": "150.00"}

    assert extrair_detail(payload_negocio) == payload_negocio
