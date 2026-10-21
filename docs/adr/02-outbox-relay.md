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
Para este desafio, implementamos a **opção 2 — Outbox com relay por
polling**, rodando tanto localmente quanto no manifesto de referência
para EKS. A tabela de outbox e a garantia de atomicidade (abaixo) são a
parte que **não muda** entre as duas opções — a única diferença entre
elas é *quem* lê a tabela e leva o evento até o EventBridge.

Motivos para a escolha neste desafio:
- **Portabilidade local:** o desafio exige execução local via kind +
  LocalStack. O suporte a DynamoDB Streams + EventBridge Pipes no
  LocalStack (community) é limitado/instável, o que comprometeria a
  demonstração fim-a-fim exigida na defesa técnica.
- **Simplicidade operacional e didática:** um worker simples (polling +
  publish + marcar como enviado) é mais fácil de testar, depurar e
  explicar do que uma cadeia de recursos gerenciados encadeados (Stream →
  Pipe → Enrichment → Target), reduzindo superfície de falha para o
  escopo deste desafio.
- **Controle explícito de retry/backoff e DLQ:** o relay decide
  explicitamente a política de nova tentativa e quando mover um evento
  para uma fila de letra morta, em vez de depender do comportamento
  padrão do serviço gerenciado.
- **Garantia de atomicidade:** como o registro de outbox é gravado no
  mesmo `TransactWriteItems` do agregado, nunca há evento publicado sem
  que o estado correspondente tenha sido persistido (nem o inverso).

### Em produção real na AWS, a escolha seria a opção 1
Fora do contexto do desafio, numa conta AWS real, a recomendação seria
migrar o passo de entrega para **DynamoDB Streams + EventBridge Pipes**,
mantendo a mesma tabela de outbox e o mesmo contrato de evento. Motivos:
- São serviços **nativos e totalmente gerenciados** pela AWS: sem worker
  próprio para manter disponível, sem pod para dimensionar/atualizar,
  sem lógica de polling para operar.
- Patch/upgrade, alta disponibilidade e escala do próprio Stream/Pipe
  ficam por conta da AWS, reduzindo a superfície operacional da squad.
- Menor latência de entrega (reação a mudanças quase em tempo real, em
  vez de esperar o intervalo de polling).

O trade-off que viria junto, e que eu documentaria explicitamente:
- **Retenção do Stream é de 24h.** Se o Pipe ficar indisponível (ex.:
  destino fora do ar, erro de mapeamento) por mais tempo que isso sem
  ninguém perceber, os registros mais antigos do Stream são perdidos
  definitivamente — diferente do polling, em que o evento continua
  esperando na tabela de outbox indefinidamente até ser publicado.
- Isso exige DLQ configurada no Pipe **e** alarme de CloudWatch
  monitorando falhas/atraso, para garantir que alguém seja acionado
  bem antes de bater no limite de 24h.
- Controle de retry/backoff passa a ser o padrão do Pipe (configurável,
  mas menos granular do que a lógica própria do relay).

Ou seja: a implementação entregue usa polling (pela restrição do
ambiente local do desafio); a decisão de arquitetura para produção real
seria Streams + EventBridge Pipes, com os devidos alarmes de DLQ/retenção
como mitigação do risco das 24h.

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
- Neste desafio (local e manifesto de referência para EKS), o worker de
  relay (`services/outbox-relay`) é *stateless* e pode escalar
  horizontalmente; usa `ConditionExpression` ao marcar um registro como
  "em processamento" para evitar publicação duplicada entre réplicas
  (ainda assim, consumidores devem ser idempotentes por `event_id`, pois a
  entrega é *at-least-once* em ambas as opções — polling ou Pipes).
- No manifesto de referência para EKS, o relay roda como Deployment com
  KEDA escalando conforme o tamanho da fila de outbox pendente (ver ADR
  05) — essa parte de autoscaling deixa de existir se a entrega migrar
  para Streams + Pipes, já que não há mais worker próprio para escalar.
- Caminho de evolução para produção real: migrar a entrega para DynamoDB
  Streams + EventBridge Pipes (ver seção acima), sem alterar o contrato de
  evento publicado nem os consumidores — a tabela de outbox e a escrita
  atômica continuam as mesmas, só muda quem lê e publica.
