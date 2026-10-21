# Sequência — Autorização de Transação (saga leve)

Cobre o caminho feliz (aprovação), a recusa por limite insuficiente, e o
caso de falha indeterminada (timeout/5xx) tratado pela saga (ver ADR 04).

```mermaid
sequenceDiagram
    autonumber
    participant C as Estabelecimento
    participant A as Serviço de Autorização
    participant IDP as Tabela Idempotência
    participant L as Serviço de Limites
    participant OUT as Outbox (DynamoDB)

    C->>A: POST /v1/contratos/{id}/autorizacoes<br/>Idempotency-Key: k1
    A->>IDP: busca(k1)
    alt chave já processada (mesmo payload)
        IDP-->>A: resultado anterior
        A-->>C: 200 (resultado idempotente)
    else chave em processamento (outra requisição concorrente)
        IDP-->>A: em andamento
        A-->>C: 409 Conflict ("tente novamente")
    else nova requisição
        IDP-->>A: não encontrado
        A->>A: cria Autorizacao (status=PENDENTE, id_autorizacao determinístico)
        A->>L: aplicar_operacao(id_contrato, id_autorizacao, valor)<br/>(idempotente por id_autorizacao)
        alt saldo suficiente
            L-->>A: 201 reserva efetivada (saldo_reservado)
            A->>A: Autorizacao -> APROVADA
            A->>OUT: grava RegistroOutbox(TransacaoAutorizada, status=PENDENTE)
            A->>IDP: salva(k1, resultado=APROVADA)
            A-->>C: 201 Created (APROVADA)
        else saldo insuficiente
            L-->>A: 402 limite insuficiente
            A->>A: Autorizacao -> RECUSADA
            A->>IDP: salva(k1, resultado=RECUSADA)
            A-->>C: 402 Payment Required (RECUSADA)
        else timeout/5xx (indeterminado)
            L--xA: timeout / 5xx
            A->>A: Autorizacao permanece PENDENTE
            A-->>C: 409 Conflict ("ainda em andamento")
            Note over A,L: Sweeper reconcilia depois,<br/>consultando a reserva por id_autorizacao
        end
    end
```

## Notas

- `id_autorizacao` é determinístico a partir da `Idempotency-Key` (hash), permitindo reenviar a mesma reserva com segurança.
- A reserva em Limites usa `TransactWriteItems` com condição `saldo_reservado + valor <= limite_total` (ver ADR 03) — a concorrência entre autorizações do mesmo contrato é resolvida atomicamente lá, não em Autorização.
- O corpo 409 e 402 segue RFC 7807 (`application/problem+json`), ver `contracts/openapi.yaml`.
