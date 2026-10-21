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
A reserva de limite é feita com **DynamoDB `TransactWriteItems`**, usando
uma condição atômica que impede a violação da invariante acima sem
precisar de lock externo.

**Modelo de dados (implementação real):** a tabela `limites` tem apenas
partition key (`pk` = `id_contrato`), sem sort key — por isso o agregado
inteiro (`limite_total`, `saldo_reservado` e o mapa de `reservas` por
`id_autorizacao`) é persistido como **um único item por contrato**, em vez
de itens separados para limite/reserva/outbox. A gravação ainda usa
`transact_write_items` (um único `Put` com `ConditionExpression`) para
deixar explícito, no código do adapter
(`services/limites/src/infrastructure/dynamodb_repository.py`), que o
mecanismo de concorrência é o mesmo primitivo transacional do DynamoDB, e
para manter a porta aberta a uma futura divisão em itens caso surja a
necessidade de consultá-los individualmente (ex. GSI por status de
reserva).

O fluxo de escrita:

1. Lê o item do contrato (`saldo_reservado` atual).
2. Aplica a operação em memória no agregado `Limite` (que já valida
   `saldo_reservado + valor <= limite_total` antes de gravar).
3. Grava o item inteiro de volta via `transact_write_items`, com
   `ConditionExpression saldo_reservado = :valor_lido` — se outro
   processo já tiver alterado o saldo entre a leitura e a escrita, a
   condição falha (`TransactionCanceledException`) e o repositório
   relança como `ConflitoConcorrenciaError` (409), sem nunca aplicar a
   operação duas vezes.
4. A publicação do evento de domínio (`TransacaoAutorizada`) na outbox é
   uma escrita separada, feita pelo Serviço de Autorização (não faz parte
   desta mesma transação — ver ADR 02 e ADR 04 sobre a saga leve entre os
   dois serviços/bancos).

Se a condição falhar, a API retorna:
- **402 Payment Required** quando a causa é limite insuficiente (regra de
  negócio, validada antes mesmo de tentar escrever).
- **409 Conflict** quando a causa é concorrência genuína detectada pelo
  DynamoDB (`TransactionCanceledException` por `ConditionalCheckFailed` em
  cenário de corrida), permitindo ao cliente decidir se tenta novamente.

A liberação de reserva (estorno) usa o mesmo mecanismo em sentido inverso:
decremento condicional de `saldo_reservado`, nunca permitindo valor
negativo.

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
