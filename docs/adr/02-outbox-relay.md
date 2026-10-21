# ADR 02 — Entrega confiável de eventos: Transactional Outbox com relay por polling

## Status
Aceito

## Contexto
Após autorizar uma transação, o serviço precisa publicar o evento
`TransacaoAutorizada` (e eventos equivalentes para limite alterado e
estorno) para o Amazon EventBridge, de onde fan-out ocorre via regras para
SNS/SQS. É inaceitável perder eventos (gera divergência contábil) ou
publicá-los antes de confirmar a escrita local (geraria eventos "fantasma"
em caso de rollback).

Duas alternativas foram avaliadas:

1. **DynamoDB Streams + EventBridge Pipes**: captura de mudanças na tabela
   e transformação/roteamento declarativo para o EventBridge.
2. **Tabela de Outbox + worker de relay por polling**: o agregado escreve
   o evento de domínio em uma tabela `outbox` na mesma transação
   (`TransactWriteItems`) que persiste o próprio agregado; um worker
   separado lê a tabela periodicamente, publica no EventBridge e marca o
   registro como publicado.

## Decisão
Adotamos a **opção 2 — Outbox com relay por polling**.

Motivos:
- **Portabilidade local:** o desafio exige execução local via kind +
  LocalStack. O suporte a DynamoDB Streams + EventBridge Pipes no
  LocalStack (community) é limitado/instável, o que comprometeria a
  demonstração fim-a-fim exigida na defesa técnica.
- **Simplicidade operacional:** um worker simples (polling + publish +
  marcar como enviado) é mais fácil de testar, depurar e explicar do que
  uma cadeia de recursos gerenciados encadeados (Stream → Pipe →
  Enrichment → Target), reduzindo superfície de falha para o escopo deste
  desafio.
- **Controle explícito de retry/backoff e DLQ:** o relay decide
  explicitamente a política de nova tentativa e quando mover um evento
  para uma fila de letra morta, em vez de depender do comportamento
  padrão do serviço gerenciado.
- **Garantia de atomicidade:** como o registro de outbox é gravado no
  mesmo `TransactWriteItems` do agregado, nunca há evento publicado sem
  que o estado correspondente tenha sido persistido (nem o inverso).

**Implementação:** `DynamoDbAutorizacaoRepository.salvar_com_evento`
(`services/autorizacao/src/infrastructure/dynamodb_repository.py`) grava
numa única `transact_write_items` cruzando as tabelas `autorizacoes` e
`autorizacao-outbox`; se a transação falhar, nenhuma das duas escritas é
aplicada. O caso de uso (`autorizar_transacao.py` /
`estornar_autorizacao.py`) chama este método só quando a autorização é
aprovada (único momento em que há evento a publicar); as demais escritas
(pendente/recusada) seguem sendo `put_item` isolados, por não haver
invariante entre tabelas a proteger nesses casos.

## Consequências
- Há uma pequena latência adicional entre a escrita do agregado e a
  publicação do evento (intervalo de polling, ex. 1–2s) — aceitável para
  consumidores assíncronos (contabilidade, antifraude, notificações).
- O worker de relay (`services/outbox-relay`) é *stateless* e pode escalar
  horizontalmente; usa `ConditionExpression` ao marcar um registro como
  "em processamento" para evitar publicação duplicada entre réplicas
  (ainda assim, consumidores devem ser idempotentes por `event_id`, pois a
  entrega é *at-least-once*).
- Em produção (EKS), o relay roda como Deployment com KEDA escalando
  conforme o tamanho da fila de outbox pendente (ver ADR 05).
- Caminho de evolução: se a volumetria justificar, a tabela de outbox pode
  futuramente ser alimentada por Streams nativamente, sem alterar o
  contrato de evento publicado nem os consumidores.
