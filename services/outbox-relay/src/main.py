"""Entrypoint do container `outbox-relay` (produção / kind+LocalStack).

Lê configuração via variáveis de ambiente e roda o `RelayWorker` em loop
contínuo, publicando no EventBridge a partir da tabela DynamoDB de outbox
do serviço configurado em `OUTBOX_TABLE_NAME`. Não é exercitado por
testes unitários — depende de infraestrutura real (DynamoDB/EventBridge);
a lógica testável vive em `worker.py`.
"""
from __future__ import annotations

import logging
import os

from .dynamodb_outbox_source import DynamoDbOutboxSource
from .eventbridge_publisher import EventBridgePublisher
from .metrics_server import iniciar_servidor_metricas
from .worker import RelayWorker

logger = logging.getLogger("outbox_relay.main")


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    source = DynamoDbOutboxSource()
    publisher = EventBridgePublisher()
    worker = RelayWorker(source, publisher)
    iniciar_servidor_metricas(source, porta=int(os.environ.get("METRICS_PORT", "9090")))
    intervalo = float(os.environ.get("RELAY_POLL_INTERVAL_SECONDS", "2"))
    logger.info("outbox-relay iniciado, intervalo=%ss", intervalo)
    worker.run_forever(intervalo_segundos=intervalo)


if __name__ == "__main__":  # pragma: no cover
    main()
