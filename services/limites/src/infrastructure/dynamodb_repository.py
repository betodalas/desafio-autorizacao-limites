"""Adapter real de persistência do agregado `Limite` em DynamoDB (ver ADR
03), usado quando o serviço roda no cluster (k8s + LocalStack/AWS) — ver
seleção em `api.py`.

Modelo: um único item por contrato (`pk = "CONTRATO#<id_contrato>"`)
guardando `limite_total`, `saldo_reservado` e um mapa `reservas` (uma
entrada por `id_autorizacao` já aplicada, para idempotência). Como é um
único item, a escrita via `transact_write_items` com uma
`ConditionExpression` sobre o `saldo_reservado` lido garante controle de
concorrência otimista: se outro processo alterou o contrato entre a
leitura e a gravação, a condição falha e levantamos
`ConflitoConcorrenciaError` (HTTP 409) — o chamador deve tentar de novo.
Isso preserva a invariante `saldo_reservado + valor <= limite_total` sob
concorrência real, sem precisar de lock distribuído externo.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from ..domain.events import LimiteOperacaoAplicada
from ..domain.exceptions import ConflitoConcorrenciaError
from ..domain.limite import Limite, Reserva
from ..domain.repository import LimiteRepository
from ..domain.value_objects import Money, TipoOperacao


class DynamoDbLimiteRepository(LimiteRepository):
    def __init__(self, table_name: str | None = None):
        endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
        region = os.environ.get("AWS_REGION", "us-east-1")
        self._resource = boto3.resource("dynamodb", endpoint_url=endpoint_url, region_name=region)
        self._client = boto3.client("dynamodb", endpoint_url=endpoint_url, region_name=region)
        self._table_name = table_name or os.environ.get("LIMITES_TABLE_NAME", "limites")
        self._table = self._resource.Table(self._table_name)
        # saldo "cru" lido por contrato, usado como expected-value na
        # condição otimista de `salvar` — vive só durante a vida da
        # requisição (uma instância de repository por request/processo).
        self._saldo_lido: dict[str, str] = {}

    @staticmethod
    def _pk(id_contrato: str) -> str:
        return f"CONTRATO#{id_contrato}"

    def buscar_por_contrato(self, id_contrato: str) -> Optional[Limite]:
        resposta = self._table.get_item(Key={"pk": self._pk(id_contrato)})
        item = resposta.get("Item")
        if item is None:
            return None

        limite = Limite(id_contrato=id_contrato, limite_total=Money.from_str(item["limite_total"]))
        saldo_str = item["saldo_reservado"]
        self._saldo_lido[id_contrato] = saldo_str
        limite._saldo_reservado = Money.from_str(saldo_str)  # noqa: SLF001 - reconstrução do agregado

        for id_autorizacao, dados in item.get("reservas", {}).items():
            evento_dados = dados["evento"]
            evento = LimiteOperacaoAplicada(
                id_contrato=id_contrato,
                id_autorizacao=id_autorizacao,
                tipo_operacao=TipoOperacao(evento_dados["tipo_operacao"]),
                valor=Money.from_str(evento_dados["valor"]),
                saldo_reservado=Money.from_str(evento_dados["saldo_reservado"]),
                limite_total=limite.limite_total,
                ocorrido_em=datetime.fromisoformat(evento_dados["ocorrido_em"]),
            )
            limite._reservas[id_autorizacao] = Reserva(  # noqa: SLF001
                id_autorizacao=id_autorizacao,
                tipo_operacao=TipoOperacao(dados["tipo_operacao"]),
                valor=Money.from_str(dados["valor"]),
                evento=evento,
            )
        return limite

    def salvar(self, limite: Limite) -> None:
        reservas_serializadas = {
            id_autorizacao: {
                "tipo_operacao": reserva.tipo_operacao.value,
                "valor": str(reserva.valor),
                "evento": {
                    "tipo_operacao": reserva.evento.tipo_operacao.value,
                    "valor": str(reserva.evento.valor),
                    "saldo_reservado": str(reserva.evento.saldo_reservado),
                    "ocorrido_em": reserva.evento.ocorrido_em.isoformat(),
                },
            }
            for id_autorizacao, reserva in limite._reservas.items()  # noqa: SLF001
        }

        item = {
            "pk": self._pk(limite.id_contrato),
            "limite_total": str(limite.limite_total),
            "saldo_reservado": str(limite.saldo_reservado),
            "reservas": reservas_serializadas,
        }

        saldo_esperado = self._saldo_lido.get(limite.id_contrato)
        if saldo_esperado is None:
            # Primeira escrita do contrato (cadastro de limite, ver
            # `cadastrar_limite` em api.py): não há condição de
            # concorrência a proteger, só evita sobrescrever um contrato
            # já existente criado entre a checagem e esta chamada.
            self._table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(pk) OR saldo_reservado = :zero",
                ExpressionAttributeValues={":zero": "0.00"},
            )
            return

        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self._table_name,
                            "Item": {
                                "pk": {"S": item["pk"]},
                                "limite_total": {"S": item["limite_total"]},
                                "saldo_reservado": {"S": item["saldo_reservado"]},
                                "reservas": {"M": _serializar_reservas_dynamo(reservas_serializadas)},
                            },
                            "ConditionExpression": "saldo_reservado = :esperado",
                            "ExpressionAttributeValues": {":esperado": {"S": saldo_esperado}},
                        }
                    }
                ]
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "TransactionCanceledException":
                raise ConflitoConcorrenciaError(
                    f"Contrato {limite.id_contrato!r} foi alterado concorrentemente; tente novamente"
                ) from exc
            raise


def _serializar_reservas_dynamo(reservas: dict) -> dict:
    """Converte o dict Python de reservas para o formato de atributo
    DynamoDB (`AttributeValue`) exigido pela API de baixo nível usada em
    `transact_write_items` (o `resource` de alto nível não participa de
    transações multi-item, mas aqui usamos 1 item só mesmo assim para
    manter a chamada literal a `TransactWriteItems`, conforme ADR 03)."""
    return {
        id_autorizacao: {
            "M": {
                "tipo_operacao": {"S": dados["tipo_operacao"]},
                "valor": {"S": dados["valor"]},
                "evento": {
                    "M": {
                        "tipo_operacao": {"S": dados["evento"]["tipo_operacao"]},
                        "valor": {"S": dados["evento"]["valor"]},
                        "saldo_reservado": {"S": dados["evento"]["saldo_reservado"]},
                        "ocorrido_em": {"S": dados["evento"]["ocorrido_em"]},
                    }
                },
            }
        }
        for id_autorizacao, dados in reservas.items()
    }
