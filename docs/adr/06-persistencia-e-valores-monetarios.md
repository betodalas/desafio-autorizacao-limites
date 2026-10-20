# ADR 06 — Persistência: DynamoDB (database-per-service) e representação de valores monetários

## Status
Aceito

## Contexto
É necessário escolher a estratégia de persistência por serviço e o
formato de representação de valores monetários nas APIs e eventos.

## Decisão

### Persistência
Cada serviço possui seu próprio armazenamento (database-per-service):

- **Limites:** Amazon DynamoDB. Acesso é majoritariamente por chave
  (`id_contrato`), com necessidade de escrita condicional atômica de alto
  throughput (ADR 03) — perfil ideal para DynamoDB.
- **Autorização:** Amazon DynamoDB. Mesmo perfil de acesso por chave
  (`id_autorizacao`, `idempotency_key`), com TTL nativo para expurgo de
  registros de idempotência.
- **Contabilização:** Amazon DynamoDB para os lançamentos contábeis
  derivados de eventos (chave `event_id` para idempotência do
  consumidor). Um modelo relacional (Aurora) seria razoável caso surjam
  consultas analíticas/ad-hoc complexas sobre lançamentos — não é o caso
  neste escopo, onde a leitura é majoritariamente por chave/replicação
  para a data platform via eventos.
- **Outbox:** tabela DynamoDB dedicada por serviço produtor
  (`autorizacao-outbox`, `limites-outbox`), para preservar a atomicidade
  com o agregado (ADR 02).

### Representação de valores monetários
Valores monetários (`valor`, `saldo_reservado`, `limite_total`) são
transportados como **string decimal de duas casas** (ex. `"150.00"`) tanto
nos contratos de API (OpenAPI) quanto no contrato de evento, e internamente
manipulados em Python com `decimal.Decimal`, nunca `float`.

Justificativa: `float`/`double` têm representação binária imprecisa para
frações decimais (ex. `0.1 + 0.2 != 0.3`), o que é inaceitável para
cálculos financeiros auditáveis. Usar string na borda evita também que
clientes de linguagens com JSON number nativo (ex. JavaScript) percam
precisão ao desserializar.

## Consequências
- Todo código de domínio usa `Decimal` com contexto de arredondamento
  explícito (`ROUND_HALF_UP`, 2 casas) nas fronteiras de entrada/saída.
- DynamoDB armazena os valores monetários como `Number` (DynamoDB usa
  internamente uma representação decimal de alta precisão, sem os
  problemas de `float` de outras linguagens), convertido para/de
  `Decimal` nos adapters de repositório.
- Testes de domínio cobrem casos de arredondamento e limites de
  precisão para evitar regressões.
