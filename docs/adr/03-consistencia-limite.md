# ADR 03 — Consistência do agregado Limite sob concorrência (TransactWriteItems)

## Status
Aceito

## Contexto
O agregado `Limite` possui a invariante:

```
saldo_reservado + valor <= limite_total
```

Múltiplas autorizações para o mesmo contrato podem chegar concorrentemente
(ex. compras simultâneas no mesmo cartão/conta). Sem controle de
concorrência adequado, duas reservas simultâneas poderiam, juntas,
ultrapassar o limite total (condição de corrida clássica de
leitura-depois-escrita).

## Decisão
A reserva de limite é feita com **DynamoDB `TransactWriteItems`**, em uma
única operação condicional que:

1. Atualiza o item `Limite` incrementando `saldo_reservado` em `valor`,
   **com `ConditionExpression`**:
   `saldo_reservado + :valor <= limite_total` (avaliada atomicamente pelo
   próprio DynamoDB, sem leitura prévia fora da transação).
2. Cria, na mesma transação, o item de **reserva** (`id_autorizacao` como
   chave), com `ConditionExpression attribute_not_exists(id_autorizacao)`
   — garante idempotência: uma segunda tentativa com o mesmo
   `id_autorizacao` falha a condição e não soma o valor duas vezes.
3. Insere, na mesma transação, o registro de **outbox** com o evento de
   domínio (`LimiteReservado`), garantindo atomicidade entre estado e
   evento (ver ADR 02).

Se a condição falhar, a API retorna:
- **402 Payment Required** quando a causa é limite insuficiente (regra de
  negócio).
- **409 Conflict** quando a causa é concorrência genuína detectada pelo
  DynamoDB (`TransactionCanceledException` por `ConditionalCheckFailed` em
  cenário de corrida), permitindo ao cliente decidir se tenta novamente.

A liberação de reserva (estorno) usa o mesmo mecanismo em sentido inverso:
decremento condicional de `saldo_reservado`, nunca permitindo valor
negativo (`saldo_reservado - :valor >= 0`).

## Alternativas consideradas
- **Lock otimista com campo de versão + retry no cliente:** rejeitado
  porque exigiria leitura + escrita em duas chamadas, abrindo uma janela
  de corrida que teria que ser fechada mesmo assim por uma condição
  atômica — `TransactWriteItems` já resolve isso em uma única chamada.
- **Lock pessimista (ex. registro de lock distribuído):** rejeitado por
  adicionar latência e um ponto de contenção que não escala para ~5.000
  TPS de pico.

## Consequências
- A validação de negócio (limite insuficiente) e a validação de
  concorrência (corrida real) usam o mesmo mecanismo transacional, mas
  retornam códigos HTTP diferentes — o adapter de API inspeciona a causa
  retornada pelo DynamoDB (`CancellationReasons`) para diferenciar 402 de
  409.
- A escrita é O(1) em capacidade de leitura/escrita do DynamoDB
  (sem necessidade de scan ou lock externo), compatível com o SLA de
  ~5.000 TPS de pico.
