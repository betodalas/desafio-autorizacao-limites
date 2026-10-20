# ADR 01 — Domain-Driven Design: Bounded Contexts, Agregados e Linguagem Ubíqua

## Status
Aceito

## Contexto
A plataforma precisa validar e autorizar transações financeiras em tempo real,
gerenciar limites de crédito por contrato sob alta concorrência, e publicar
eventos contábeis para consumidores desacoplados (contabilidade, antifraude,
notificações, data platform). O domínio envolve múltiplos conceitos que, se
modelados como um monólito único, geram acoplamento indevido entre regras de
negócio com taxas de mudança e times donos diferentes.

## Decisão
Dividimos o domínio em três bounded contexts, cada um com seu próprio
agregado raiz, modelo de dados e serviço:

### 1. Contexto de Limites (`services/limites`)
- **Agregado raiz:** `Limite` (por contrato).
- **Invariante central:** `saldo_reservado + valor <= limite_total` sempre,
  mesmo sob concorrência (múltiplas autorizações simultâneas no mesmo
  contrato).
- **Responsabilidade:** reservar, liberar e consultar limite disponível.
  Não conhece o conceito de "transação" ou "estabelecimento" — apenas reservas
  de valor identificadas por `id_autorizacao`.
- **Persistência:** Amazon DynamoDB, com `TransactWriteItems` condicional
  para garantir a invariante atomicamente (ver ADR 03).

### 2. Contexto de Autorização (`services/autorizacao`)
- **Agregado raiz:** `Autorizacao`.
- **Responsabilidade:** orquestrar o fluxo síncrono de autorização —
  validar o payload, solicitar reserva de limite, decidir
  aprovação/recusa, e publicar o evento `TransacaoAutorizada`. Trata
  idempotência via `Idempotency-Key` e processa estornos
  (`id_autorizacao_original`).
- **Persistência:** DynamoDB (tabela de autorizações + tabela de
  idempotência).
- **Relação com Limites:** são bounded contexts com bancos de dados
  diferentes; não há transação distribuída ACID entre eles. A consistência
  é garantida por uma saga leve orientada a estado (ver ADR 04).

### 3. Contexto de Contabilização (`services/contabilizacao`)
- **Agregado raiz:** `LancamentoContabil`.
- **Responsabilidade:** consumir `TransacaoAutorizada` (e demais eventos de
  domínio) e gerar lançamentos contábeis, de forma assíncrona e
  desacoplada do fluxo síncrono de autorização.
- **Padrão tático:** consumidor idempotente por `event_id`, tolerante a
  reordenação e reentrega.

### Serviço de suporte: Outbox Relay (`services/outbox-relay`)
- Não é um bounded context de negócio, mas um componente de infraestrutura
  compartilhado que garante a publicação confiável de eventos de domínio
  (padrão Transactional Outbox — ver ADR 02).

## Linguagem Ubíqua (glossário)
| Termo | Significado |
|---|---|
| Contrato | Relação jurídica entre o banco e o cliente que carrega um limite (crédito, investimento, seguros, consórcio) |
| Limite | Teto de exposição financeira associado a um contrato |
| Saldo reservado | Parcela do limite comprometida por autorizações ainda não liquidadas/estornadas |
| Autorização | Decisão (aprovada/recusada) sobre uma transação, tomada em tempo real |
| Reserva | Ato de comprometer saldo de limite para uma autorização específica |
| Estorno | Operação que libera (total ou parcialmente) uma reserva feita por uma autorização anterior |
| Tipo de operação | DEBITO, CREDITO, RESERVA, ESTORNO — cada um com política própria de impacto no limite |

## Padrões táticos e trade-offs

- **CQRS:** **não adotado** nesta entrega. O volume de leitura de limite é
  dominado pela própria escrita (toda autorização lê e escreve limite na
  mesma operação), então separar modelos de leitura/escrita adicionaria
  complexidade (projeções, consistência eventual) sem ganho claro no escopo
  do desafio. Revisitar se surgir um caso de uso de consulta de limite em
  massa/relatórios com SLA distinto do de escrita.
- **Repository:** adotado como *port* no domínio (`LimiteRepository`,
  `AutorizacaoRepository`), com adapter DynamoDB na infraestrutura —
  permite testar o domínio sem AWS (ver `services/limites/tests`).
- **Domain Events:** adotado. `Limite` e `Autorizacao` emitem eventos de
  domínio internos (ex. `LimiteReservado`, `AutorizacaoAprovada`) que são
  persistidos na tabela de outbox na mesma transação de escrita do
  agregado, e publicados de forma assíncrona (ver ADR 02).

## Consequências
- Cada serviço pode escalar, implantar e evoluir de forma independente
  (database-per-service).
- Para manter consistência entre Limite e Autorização sem transação
  distribuída, é necessário um mecanismo de reconciliação (sweeper) para
  tratar reservas pendentes em caso de falha parcial (ver ADR 04).
- Introduz a necessidade de um serviço técnico (outbox relay) e disciplina
  de idempotência em todos os consumidores de evento.
