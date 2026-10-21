# Fluxo do Evento — Outbox → Relay → EventBridge → SQS → Contabilização

```mermaid
sequenceDiagram
    autonumber
    participant A as Autorização (use case)
    participant OUT as Outbox (DynamoDB, GSI status-index)
    participant R as outbox-relay (worker)
    participant EB as EventBridge (bus financas-eventos)
    participant Q as SQS (contabilizacao + DLQ)
    participant CT as Contabilização (consumer)
    participant DB as Lançamentos (dedup por event_id)

    A->>OUT: salvar(RegistroOutbox: PENDENTE, event_id, payload)
    loop polling (run_forever, intervalo configurável)
        R->>OUT: listar_pendentes(status=PENDENTE) via GSI
        OUT-->>R: [registros...]
        R->>EB: put_events(detail-type=TransacaoAutorizada)
        alt publicação OK
            EB-->>R: sucesso
            R->>OUT: marcar_publicado(event_id)
        else falha (timeout/erro)
            EB--xR: erro
            R->>OUT: marcar_falha(event_id)<br/>(mantém PENDENTE até max_tentativas)
            Note over R,OUT: Após max_tentativas, status final = FALHA<br/>(equivalente a uma DLQ lógica da outbox)
        end
    end
    EB->>Q: regra de roteamento entrega na fila
    Q->>CT: poll/receive
    CT->>DB: buscar_por_event_id(event_id)
    alt já processado
        DB-->>CT: lançamento existente
        CT->>CT: no-op idempotente
    else novo evento
        DB-->>CT: não encontrado
        CT->>DB: salvar(LancamentoContabil)
    end
    CT->>Q: delete_message (ack)
    Note over Q: Mensagens que falham `maxReceiveCount` vezes<br/>na Contabilização vão para a DLQ (ver terraform/modules/sqs)
```

## Notas

- O **worker outbox-relay é genérico** (ports `OutboxSource`/`EventPublisher`) — hoje lê apenas a outbox de Autorização, mas o mesmo binário poderia ler a outbox de qualquer outro bounded context que a implementasse.
- `/metrics` do outbox-relay expõe `{"pendentes": N}` (contagem de itens com `status=PENDENTE`), consumido pelo KEDA via scaler `metrics-api` para escalar o Deployment do relay.
- Contabilização escala via KEDA `aws-sqs-queue` diretamente contra a profundidade da fila — não precisa de métrica customizada.
- A idempotência em Contabilização é por `event_id` (não por conteúdo), tornando o reprocessamento de uma mensagem SQS entregue mais de uma vez (at-least-once) seguro.
