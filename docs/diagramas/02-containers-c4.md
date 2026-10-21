# C4 — Nível 2: Diagrama de Containers

```mermaid
C4Container
    title Sistema de Autorização/Limites — Containers

    Person(estabelecimento, "Estabelecimento/Adquirente")

    System_Boundary(plataforma, "Plataforma de Autorização/Limites") {
        Container(autorizacao, "autorizacao", "Python/FastAPI", "Saga de autorização/estorno, idempotência, outbox")
        ContainerDb(db_autorizacao, "autorizacoes, idempotencia, outbox", "DynamoDB", "Estado da Autorização + outbox transacional")

        Container(limites, "limites", "Python/FastAPI", "Agregado Limite, reserva/libera saldo via TransactWriteItems")
        ContainerDb(db_limites, "limites", "DynamoDB", "Single-table: contrato + reservas por id_autorizacao")

        Container(relay, "outbox-relay", "Python (worker)", "Lê outbox PENDENTE, publica no EventBridge, expõe /metrics para KEDA")

        Container(contabilizacao, "contabilizacao", "Python (worker SQS)", "Consome TransacaoAutorizada de forma idempotente")
        ContainerDb(db_contabilizacao, "lancamentos", "DynamoDB (em memória na demo)", "Lançamentos contábeis, dedup por event_id")

        Container(bus, "financas-eventos", "EventBridge", "Bus de eventos de domínio")
        Container(fila, "contabilizacao (+ DLQ)", "SQS", "Fila de entrega do evento TransacaoAutorizada")
    }

    Rel(estabelecimento, autorizacao, "autoriza/estorna", "HTTPS/JSON")
    Rel(autorizacao, db_autorizacao, "lê/escreve (TransactWriteItems)")
    Rel(autorizacao, limites, "reserva/libera saldo", "HTTPS/JSON (interno)")
    Rel(limites, db_limites, "lê/escreve (TransactWriteItems)")
    Rel(relay, db_autorizacao, "consulta GSI status-index (PENDENTE)")
    Rel(relay, bus, "put_events")
    Rel(bus, fila, "regra de roteamento (detail-type=TransacaoAutorizada)")
    Rel(fila, contabilizacao, "poll/consume")
    Rel(contabilizacao, db_contabilizacao, "upsert idempotente por event_id")
```

## Notas

- Cada bounded context tem seu **próprio banco de dados** (ver ADR 01) — não há acesso cross-service a tabelas.
- `autorizacao` → `limites` é uma chamada **síncrona** (HTTP interno); todo o resto é **assíncrono** via outbox/EventBridge/SQS.
- `outbox-relay` é um worker **genérico**: depende apenas dos ports `OutboxSource`/`EventPublisher` — hoje só lê a outbox de `autorizacao`, mas poderia ser reaproveitado por outro bounded context no futuro sem alterações de código (apenas nova configuração de wiring).
- Em produção (EKS), `relay` escala via KEDA `metrics-api` contra seu próprio `/metrics`; `contabilizacao` escala via KEDA `aws-sqs-queue` contra a profundidade da fila — ver ADR 05 e `deploy/k8s/`.
