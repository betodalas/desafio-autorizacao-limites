"""Adapter de `OutboxSource` sobre uma tabela DynamoDB (produção/LocalStack).

Schema esperado da tabela (ver `terraform/modules/dynamodb`):
- `event_id` (partition key) — identificador único do registro de outbox.
- GSI `status-index`: partition key `status`, sort key `criado_em` — usada
  para listar pendentes sem fazer `Scan` completo da tabela.

Usa `update_item` com `ConditionExpression` para marcar um registro como
"em processamento" antes de publicar, evitando publicação duplicada caso
duas réplicas do relay leiam o mesmo lote (o KEDA pode escalar o
Deployment horizontalmente — ver ADR 05).
"""
from __future__ import annotations

import os

import boto3
from boto3.dynamodb.conditions import Key

from .ports import OutboxSource


class _RegistroDynamo:
    def __init__(self, item: dict):
        self._item = item
        self.event_id = item["event_id"]
        self.tentativas = int(item.get("tentativas", 0))

    def para_envelope(self) -> dict:
        return self._item["envelope"]


class DynamoDbOutboxSource(OutboxSource):
    def __init__(self, table_name: str | None = None):
        endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
        resource = boto3.resource(
            "dynamodb", endpoint_url=endpoint_url, region_name=os.environ.get("AWS_REGION", "us-east-1")
        )
        self._table = resource.Table(table_name or os.environ["OUTBOX_TABLE_NAME"])

    def listar_pendentes(self, limite: int = 50) -> list[_RegistroDynamo]:
        resposta = self._table.query(
            IndexName="status-index",
            KeyConditionExpression=Key("status").eq("PENDENTE"),
            Limit=limite,
        )
        return [_RegistroDynamo(item) for item in resposta.get("Items", [])]

    def marcar_publicado(self, event_id: str) -> None:
        self._table.update_item(
            Key={"event_id": event_id},
            UpdateExpression="SET #s = :publicado",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":publicado": "PUBLICADO"},
        )

    def marcar_falha(self, event_id: str, erro: str) -> None:
        self._table.update_item(
            Key={"event_id": event_id},
            UpdateExpression="SET tentativas = tentativas + :um, ultimo_erro = :erro",
            ExpressionAttributeValues={":um": 1, ":erro": erro},
        )
