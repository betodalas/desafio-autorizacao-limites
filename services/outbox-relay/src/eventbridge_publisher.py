"""Adapter de `EventPublisher` para o Amazon EventBridge (via LocalStack
localmente). Publica o envelope do evento como `Detail` de um
`PutEvents`, com `DetailType`/`Source` convencionados para permitir regras
de roteamento no barramento (ver `terraform/modules/eventbridge`)."""
from __future__ import annotations

import json
import os

import boto3

from .ports import EventPublisher


class EventBridgePublisher(EventPublisher):
    def __init__(
        self,
        event_bus_name: str | None = None,
        source: str | None = None,
        detail_type: str = "TransacaoAutorizada",
    ):
        endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
        self._client = boto3.client(
            "events", endpoint_url=endpoint_url, region_name=os.environ.get("AWS_REGION", "us-east-1")
        )
        self._event_bus_name = event_bus_name or os.environ.get("EVENT_BUS_NAME", "financas-eventos")
        # Precisa bater com o `event_pattern.source` da regra em
        # `terraform/modules/eventbridge/main.tf` (`transacao_autorizada`),
        # senão o evento é publicado no bus mas nunca roteado para a fila
        # de Contabilização.
        self._source = source or os.environ.get("EVENT_SOURCE", "autorizacao")
        self._detail_type = detail_type

    def publicar(self, envelope: dict) -> None:
        resposta = self._client.put_events(
            Entries=[
                {
                    "EventBusName": self._event_bus_name,
                    "Source": self._source,
                    "DetailType": self._detail_type,
                    "Detail": json.dumps(envelope),
                }
            ]
        )
        if resposta.get("FailedEntryCount", 0) > 0:
            raise RuntimeError(f"Falha ao publicar no EventBridge: {resposta['Entries']}")
