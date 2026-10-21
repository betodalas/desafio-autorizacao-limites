"""Adapters reais de persistência em DynamoDB para o Serviço de
Autorização (ver ADR 02 e ADR 04), usados quando `AWS_ENDPOINT_URL` está
configurado (k8s/LocalStack) — ver seleção em `api.py`.

`DynamoDbAutorizacaoRepository.salvar_com_evento` é o ponto que fecha o
gap descrito na ADR 02: a decisão de autorização e o evento de outbox são
gravados numa única `TransactWriteItems` cruzando as tabelas
`autorizacoes` e `autorizacao-outbox` — nunca existe um estado em que a
decisão foi persistida sem o evento correspondente (ou vice-versa). As
demais escritas (`salvar` sozinho, sem evento — ex. autorização recusada
ou ainda pendente) continuam sendo `put_item` isolados, pois não há
invariante entre tabelas a proteger nesses casos.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import boto3
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from ..domain.autorizacao import Autorizacao, StatusAutorizacao
from ..domain.events import TransacaoAutorizada
from ..domain.idempotencia import RegistroIdempotencia, StatusIdempotencia
from ..domain.outbox import RegistroOutbox, StatusOutbox
from ..domain.ports import AutorizacaoRepository, IdempotenciaRepository, OutboxRepository
from ..domain.value_objects import Money, TipoOperacao
from ..domain.exceptions import OperacaoEmAndamentoError

_serializer = TypeSerializer()


def _resource():
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    region = os.environ.get("AWS_REGION", "us-east-1")
    return boto3.resource("dynamodb", endpoint_url=endpoint_url, region_name=region)


def _client():
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    region = os.environ.get("AWS_REGION", "us-east-1")
    return boto3.client("dynamodb", endpoint_url=endpoint_url, region_name=region)


def _serializar_item(item: dict) -> dict:
    return {chave: _serializer.serialize(valor) for chave, valor in item.items()}


class DynamoDbAutorizacaoRepository(AutorizacaoRepository):
    def __init__(self, table_name: str | None = None, outbox_table_name: str | None = None):
        self._table_name = table_name or os.environ.get("AUTORIZACOES_TABLE_NAME", "autorizacoes")
        self._table = _resource().Table(self._table_name)
        self._outbox_table_name = outbox_table_name or os.environ.get("OUTBOX_TABLE_NAME", "autorizacao-outbox")
        self._client = _client()

    def buscar(self, id_autorizacao: str) -> Optional[Autorizacao]:
        item = self._table.get_item(Key={"id_autorizacao": id_autorizacao}).get("Item")
        if item is None:
            return None
        return Autorizacao(
            id_autorizacao=item["id_autorizacao"],
            id_contrato=item["id_contrato"],
            id_conta=item["id_conta"],
            valor=Money.from_str(item["valor"]),
            moeda=item["moeda"],
            tipo_operacao=TipoOperacao(item["tipo_operacao"]),
            status=StatusAutorizacao(item["status"]),
            criado_em=datetime.fromisoformat(item["criado_em"]),
            id_autorizacao_original=item.get("id_autorizacao_original"),
            saldo_reservado=(Money.from_str(item["saldo_reservado"]) if item.get("saldo_reservado") else None),
        )

    @staticmethod
    def _item_de(autorizacao: Autorizacao) -> dict:
        item = {
            "id_autorizacao": autorizacao.id_autorizacao,
            "id_contrato": autorizacao.id_contrato,
            "id_conta": autorizacao.id_conta,
            "valor": str(autorizacao.valor),
            "moeda": autorizacao.moeda,
            "tipo_operacao": autorizacao.tipo_operacao.value,
            "status": autorizacao.status.value,
            "criado_em": autorizacao.criado_em.isoformat(),
        }
        if autorizacao.id_autorizacao_original is not None:
            item["id_autorizacao_original"] = autorizacao.id_autorizacao_original
        if autorizacao.saldo_reservado is not None:
            item["saldo_reservado"] = str(autorizacao.saldo_reservado)
        return item

    @staticmethod
    def _item_outbox_de(registro: RegistroOutbox) -> dict:
        return {
            "event_id": registro.event_id,
            "status": registro.status.value,
            "criado_em": registro.criado_em.isoformat(),
            "tentativas": registro.tentativas,
            "envelope": registro.para_envelope(),
        }

    def salvar(self, autorizacao: Autorizacao) -> None:
        self._table.put_item(Item=self._item_de(autorizacao))

    def salvar_com_evento(
        self,
        autorizacao: Autorizacao,
        registro_outbox: Optional[RegistroOutbox],
        outbox_repository: Optional[OutboxRepository] = None,
    ) -> None:
        """Grava a autorização e o evento de outbox associado numa única
        `TransactWriteItems`, cruzando as tabelas `autorizacoes` e
        `autorizacao-outbox` — fecha o gap da ADR 02 (nunca existe
        decisão persistida sem evento, nem o inverso). `outbox_repository`
        é aceito só por compatibilidade de assinatura com o fallback não
        atômico do adapter em memória; não é usado aqui."""
        if registro_outbox is None:
            self.salvar(autorizacao)
            return
        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self._table_name,
                            "Item": _serializar_item(self._item_de(autorizacao)),
                        }
                    },
                    {
                        "Put": {
                            "TableName": self._outbox_table_name,
                            "Item": _serializar_item(self._item_outbox_de(registro_outbox)),
                            "ConditionExpression": "attribute_not_exists(event_id)",
                        }
                    },
                ]
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "TransactionCanceledException":
                raise OperacaoEmAndamentoError(
                    f"Falha ao gravar atomicamente autorização {autorizacao.id_autorizacao!r} e seu evento; "
                    "tente novamente com a mesma Idempotency-Key"
                ) from exc
            raise

    def listar_pendentes_antes_de(self, limite_tempo: datetime) -> list[Autorizacao]:
        """Usado pelo sweeper (ADR 04). A tabela não tem GSI por status
        porque o sweeper roda com baixa frequência sobre um volume
        pequeno em comparação ao tráfego de autorização — um `Scan` com
        filtro é aceitável aqui; um GSI `status-index` seria o próximo
        passo caso o volume de PENDENTEs presos cresça."""
        resposta = self._table.scan(
            FilterExpression="#s = :pendente",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":pendente": StatusAutorizacao.PENDENTE.value},
        )
        resultado = []
        for item in resposta.get("Items", []):
            autorizacao = self.buscar(item["id_autorizacao"])
            if autorizacao is not None and autorizacao.criado_em < limite_tempo:
                resultado.append(autorizacao)
        return resultado


class DynamoDbIdempotenciaRepository(IdempotenciaRepository):
    def __init__(self, table_name: str | None = None):
        self._table = _resource().Table(table_name or os.environ.get("IDEMPOTENCIA_TABLE_NAME", "idempotencia"))

    def buscar(self, idempotency_key: str) -> Optional[RegistroIdempotencia]:
        item = self._table.get_item(Key={"idempotency_key": idempotency_key}).get("Item")
        if item is None:
            return None
        return RegistroIdempotencia(
            idempotency_key=item["idempotency_key"],
            hash_payload=item["hash_payload"],
            status=StatusIdempotencia(item["status"]),
            id_autorizacao=item["id_autorizacao"],
            resultado=item.get("resultado"),
        )

    def salvar(self, registro: RegistroIdempotencia) -> None:
        item = {
            "idempotency_key": registro.idempotency_key,
            "hash_payload": registro.hash_payload,
            "status": registro.status.value,
            "id_autorizacao": registro.id_autorizacao,
        }
        if registro.resultado is not None:
            item["resultado"] = registro.resultado
        self._table.put_item(Item=item)


class DynamoDbOutboxRepository(OutboxRepository):
    """Grava no mesmo schema que `outbox-relay`'s `DynamoDbOutboxSource`
    espera ler (`event_id`/`status`/`criado_em`/`envelope`, GSI
    `status-index`) — ver `services/outbox-relay/src/
    dynamodb_outbox_source.py`."""

    def __init__(self, table_name: str | None = None):
        self._table = _resource().Table(table_name or os.environ.get("OUTBOX_TABLE_NAME", "autorizacao-outbox"))

    def salvar(self, registro: RegistroOutbox) -> None:
        self._table.put_item(
            Item={
                "event_id": registro.event_id,
                "status": registro.status.value,
                "criado_em": registro.criado_em.isoformat(),
                "tentativas": registro.tentativas,
                "envelope": registro.para_envelope(),
            }
        )

    def listar_pendentes(self, limite: int = 50) -> list[RegistroOutbox]:
        # Não usado pelo serviço de Autorização em si (quem lê pendentes é
        # o worker `outbox-relay`, num processo separado); implementado
        # por completude da interface `OutboxRepository`.
        from boto3.dynamodb.conditions import Key

        resposta = self._table.query(
            IndexName="status-index",
            KeyConditionExpression=Key("status").eq(StatusOutbox.PENDENTE.value),
            Limit=limite,
        )
        resultado = []
        for item in resposta.get("Items", []):
            envelope = item["envelope"]
            evento = TransacaoAutorizada(
                id_autorizacao=envelope["id_autorizacao"],
                id_contrato=envelope["id_contrato"],
                valor=Money.from_str(envelope["valor"]),
                saldo_reservado=Money.from_str(envelope["saldo_reservado"]),
                correlation_id=envelope["correlation_id"],
                ocorrido_em=datetime.fromisoformat(envelope["occurred_at"]),
                trace_id=envelope.get("trace_id"),
            )
            resultado.append(
                RegistroOutbox(
                    event_id=item["event_id"],
                    event_type=envelope["event_type"],
                    event_version=envelope["event_version"],
                    evento=evento,
                    criado_em=datetime.fromisoformat(item["criado_em"]),
                    status=StatusOutbox(item["status"]),
                    tentativas=int(item.get("tentativas", 0)),
                )
            )
        return resultado
