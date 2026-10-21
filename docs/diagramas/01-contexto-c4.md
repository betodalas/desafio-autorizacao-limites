# C4 — Nível 1: Diagrama de Contexto

```mermaid
C4Context
    title Sistema de Autorização/Limites — Contexto

    Person(estabelecimento, "Estabelecimento/Adquirente", "Envia pedidos de autorização de transação")
    Person(backoffice, "Backoffice", "Cadastra limites de contratos (onboarding)")

    System_Boundary(plataforma, "Plataforma de Autorização/Limites") {
        System(autorizacao, "Serviço de Autorização", "API pública: autoriza e estorna transações")
        System(limites, "Serviço de Limites", "API interna: reserva/libera saldo de limite")
        System(contabilizacao, "Serviço de Contabilização", "Consome eventos de transações autorizadas")
    }

    System_Ext(aws, "AWS (DynamoDB, SQS, EventBridge)", "Infraestrutura gerenciada")

    Rel(estabelecimento, autorizacao, "POST /v1/.../autorizacoes", "HTTPS/JSON")
    Rel(backoffice, limites, "Cadastra contrato/limite", "HTTPS/JSON (interno)")
    Rel(autorizacao, limites, "Reserva/libera saldo", "HTTPS/JSON (interno, síncrono)")
    Rel(autorizacao, aws, "Grava outbox / lê-publica eventos", "DynamoDB, EventBridge")
    Rel(aws, contabilizacao, "Entrega evento TransacaoAutorizada", "SQS")
```

## Notas

- **Estabelecimento/Adquirente** é o único consumidor externo da API pública (ver `contracts/openapi.yaml`).
- **Backoffice** representa o processo de onboarding que cadastra limites — fora do escopo do desafio, modelado aqui apenas como ator de contexto (ver ADR 01).
- A comunicação entre Autorização e Limites é síncrona e interna (chamada de rede dentro da plataforma, nunca exposta externamente) — ver ADR 04 para a saga leve entre os dois bounded contexts.
- Contabilização nunca é chamada diretamente; ela reage a eventos de domínio via Outbox + Relay + EventBridge + SQS (ver ADR 02).
