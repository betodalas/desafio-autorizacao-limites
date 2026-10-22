"""Consumidor SQS (produção/LocalStack) do Serviço de Contabilização.

Faz polling na fila SQS alimentada pela regra do EventBridge que roteia
eventos `TransacaoAutorizada` (ver `terraform/modules/eventbridge` e
ADR 02), processa cada mensagem de forma idempotente e só apaga da fila
após o processamento ter sido confirmado — falhas de processamento
deixam a mensagem voltar à fila após o `visibility timeout` (e,
eventualmente, caem na DLQ configurada no Terraform).

Não é exercitado por testes unitários (depende de uma fila SQS real via
LocalStack); a lógica de negócio testada vive em
`application/processar_transacao_autorizada.py`.
"""
from __future__ import annotations

import json
import logging
import os
import time

import boto3

from ..application import ProcessarTransacaoAutorizadaUseCase
from ..domain import EventoInvalidoError
from .memory_repository import InMemoryLancamentoRepository

logger = logging.getLogger("contabilizacao.sqs_consumer")


def _cliente_sqs():
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    return boto3.client("sqs", endpoint_url=endpoint_url, region_name=os.environ.get("AWS_REGION", "us-east-1"))


def extrair_detail(body: dict) -> dict:
    """Quando a mensagem chega via EventBridge -> SQS, o corpo da mensagem
    é o *envelope* do EventBridge (`source`, `detail-type`, `detail`, ...),
    não o payload de negócio puro. O conteúdo que nos interessa está em
    `detail`. Mantém compatibilidade com testes/smoke manual que publicam
    o payload de negócio direto na fila (sem o envelope do EventBridge)."""
    if "detail" in body and "detail-type" in body:
        return body["detail"]
    return body


def executar_loop(
    queue_url: str | None = None,
    use_case: ProcessarTransacaoAutorizadaUseCase | None = None,
    max_iteracoes: int | None = None,
) -> None:
    """Loop principal do consumidor. `max_iteracoes=None` roda para
    sempre; usado com um valor finito em testes/smoke manual."""
    queue_url = queue_url or os.environ["CONTABILIZACAO_QUEUE_URL"]
    use_case = use_case or ProcessarTransacaoAutorizadaUseCase(InMemoryLancamentoRepository())
    sqs = _cliente_sqs()

    iteracoes = 0
    while max_iteracoes is None or iteracoes < max_iteracoes:
        resposta = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=5,
        )
        mensagens = resposta.get("Messages", [])
        for mensagem in mensagens:
            try:
                envelope = extrair_detail(json.loads(mensagem["Body"]))
                lancamento, criado = use_case.executar(envelope)
                logger.info(
                    "lancamento processado event_id=%s criado=%s", lancamento.event_id, criado
                )
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=mensagem["ReceiptHandle"])
            except EventoInvalidoError:
                logger.exception("evento invalido, movendo para DLQ via redrive policy")
                # Não apaga a mensagem: a redrive policy da fila (Terraform)
                # move para a DLQ após `maxReceiveCount` tentativas.
            except Exception:  # noqa: BLE001
                logger.exception("falha ao processar mensagem, sera reentregue")
        iteracoes += 1
        if not mensagens:
            time.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    executar_loop()
