# Sequência — Estorno de Autorização

```mermaid
sequenceDiagram
    autonumber
    participant C as Estabelecimento
    participant A as Serviço de Autorização
    participant IDP as Tabela Idempotência
    participant REP as Autorizações (DynamoDB)
    participant L as Serviço de Limites
    participant OUT as Outbox (DynamoDB)

    C->>A: POST /v1/.../autorizacoes/{id}/estornos<br/>Idempotency-Key: k2<br/>{id_autorizacao_original, valor, moeda}
    A->>IDP: busca(k2)
    IDP-->>A: não encontrado (nova requisição)
    A->>REP: busca(id_autorizacao_original)
    alt original não existe ou não está APROVADA
        REP-->>A: status inválido para estorno
        A-->>C: 422 (AutorizacaoOriginalInvalidaError)
    else original válida e APROVADA
        REP-->>A: Autorizacao(APROVADA, saldo_reservado)
        A->>L: aplicar_operacao(..., tipo_operacao=ESTORNO)<br/>(libera saldo previamente reservado)
        alt liberação efetivada
            L-->>A: 201 saldo liberado
            A->>A: gera nova Autorizacao de ESTORNO (APROVADA)
            A->>OUT: grava RegistroOutbox(TransacaoAutorizada, tipo=ESTORNO)
            A->>IDP: salva(k2, resultado)
            A-->>C: 201 Created (estorno aprovado)
        else operação inválida (ex. valor maior que o reservado)
            L-->>A: 422 operação inválida
            A-->>C: 422 (LimiteOperacaoInvalidaError)
        else indeterminado (timeout/5xx)
            L--xA: timeout/5xx
            A-->>C: 409 Conflict ("ainda em andamento")
        end
    end
```

## Notas

- O estorno referencia a autorização original via `id_autorizacao_original` — o campo existe especificamente para permitir rastrear a cadeia autorização → estorno (ver decisões da conversa anterior).
- Reaproveita a mesma tabela de idempotência e a mesma outbox da autorização original — um estorno também publica seu próprio evento `TransacaoAutorizada` (com `tipo_operacao=ESTORNO`), permitindo que Contabilização registre o lançamento de reversão.
