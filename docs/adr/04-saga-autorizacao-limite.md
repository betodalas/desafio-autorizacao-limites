# ADR 04 — Consistência entre Autorização e Limite: Saga leve + Idempotência + Sweeper

## Status
Aceito

## Contexto
Autorização e Limite são bounded contexts com bancos de dados distintos
(database-per-service). O fluxo síncrono de autorização precisa, em uma
única requisição:

1. Registrar a intenção de autorização.
2. Reservar o limite correspondente no Serviço de Limites.
3. Confirmar a autorização e publicar o evento `TransacaoAutorizada`.

Não há uma transação distribuída ACID cobrindo os dois serviços. Falhas
parciais são possíveis (ex. o Serviço de Autorização grava a intenção, a
chamada ao Serviço de Limites falha por timeout, mas a reserva pode ter
sido efetivada do lado de Limites antes do timeout do cliente).

## Decisão
Implementamos uma **saga leve orientada a estado**, coordenada pelo
próprio Serviço de Autorização (orquestração, não coreografia — mais fácil
de raciocinar e testar para este fluxo de 2 passos):

1. `Autorizacao` é criada no estado `PENDENTE`, com `id_autorizacao`
   gerado na borda (determinístico a partir da `Idempotency-Key`, ver
   abaixo).
2. O Serviço de Autorização chama o Serviço de Limites passando o mesmo
   `id_autorizacao` como chave de idempotência da reserva.
   - **Reserva idempotente por `id_autorizacao`**: o Serviço de Limites
     usa `attribute_not_exists(id_autorizacao)` na transação (ADR 03), de
     forma que reenviar a mesma reserva (ex. após timeout) é seguro e
     retorna o resultado já efetivado em vez de duplicar.
3. Se a reserva é aprovada, `Autorizacao` transiciona para `APROVADA` e o
   evento é gravado na outbox. Se recusada (limite insuficiente),
   transiciona para `RECUSADA`.
4. Se a chamada ao Serviço de Limites falhar de forma indeterminada
   (timeout, 5xx), a `Autorizacao` permanece `PENDENTE` e a resposta ao
   cliente é **409 Conflict** (semântica: "ainda em andamento, tente
   novamente com a mesma Idempotency-Key").
5. Um **sweeper** (job periódico) varre autorizações em `PENDENTE` há mais
   que um tempo limite configurável e reconcilia o estado consultando o
   Serviço de Limites pelo `id_autorizacao` (fonte de verdade sobre se a
   reserva foi de fato efetivada), completando a saga (`APROVADA`/
   `RECUSADA`) ou expirando a autorização se nunca houve reserva.

## Idempotência de borda (`Idempotency-Key`)
- Requisições repetidas com a **mesma chave e mesmo payload** retornam o
  resultado original (**200**), sem reprocessar.
- Requisições com a **mesma chave e payload diferente** retornam **422**
  (uso incorreto da chave de idempotência — violação de contrato).
- Requisições com a mesma chave cujo processamento original ainda está em
  andamento retornam **409**.
- A tabela de idempotência (`id_idempotencia -> hash do payload + resultado`)
  vive no Serviço de Autorização, com TTL para expurgo automático.

## Alternativas consideradas
- **Transação distribuída (2PC):** rejeitada — DynamoDB não suporta 2PC
  entre tabelas de serviços diferentes nem é recomendada para baixa
  latência em alto throughput.
- **Coreografia pura via eventos para todo o fluxo síncrono:** rejeitada
  para este caso porque a API é **síncrona** por requisito de negócio
  (decisão de aprovação/recusa em tempo real); eventos são usados para os
  efeitos colaterais assíncronos (contabilização), não para o
  core-decision.

## Consequências
- Clientes da API devem tratar 409 como "tente novamente" (idealmente com
  backoff), nunca como falha definitiva.
- O sweeper é essencial para nunca deixar uma `Autorizacao` presa em
  `PENDENTE` indefinidamente; sua cadência e timeout são configuráveis via
  ambiente.
- A reserva de limite sendo idempotente por `id_autorizacao` é o que torna
  seguro o reenvio pelo sweeper ou pelo cliente sem risco de estouro de
  limite.
