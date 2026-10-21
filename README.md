# Desafio Técnico — Arquiteto de Aplicação: Autorização/Limites

Plataforma estilo fintech para **autorização e estorno de transações com
limite de crédito**, construída com DDD (bounded contexts
database-per-service), Python (FastAPI + boto3), rodando localmente em
Kubernetes (`kind`) com `LocalStack` simulando AWS (DynamoDB, SQS,
EventBridge) e KEDA para autoscaling. IaC em Terraform. Em produção, o
mesmo design roda em EKS contra a AWS real (ver [ADR 05](docs/adr/05-runtime-eks.md)).

## Estrutura do repositório

```
services/
  autorizacao/      # Bounded context: saga de autorização/estorno, idempotência, outbox
  limites/           # Bounded context: agregado Limite (TransactWriteItems)
  contabilizacao/    # Bounded context: consumidor idempotente de eventos (SQS)
  outbox-relay/      # Worker genérico: outbox -> EventBridge, expõe /metrics p/ KEDA
contracts/
  openapi.yaml                       # Contrato da API pública (OpenAPI 3.0.3)
  events/TransacaoAutorizada.v1.schema.json  # Contrato do evento de domínio
deploy/
  kind/kind-config.yaml  # Cluster kind local, com port mappings
  k8s/                   # Namespace, config, Deployments/Services, KEDA ScaledObjects
terraform/
  modules/{dynamodb,sqs,eventbridge}/  # Módulos reutilizáveis de infraestrutura
  envs/local/                          # Ambiente local, provider apontado para o LocalStack
docs/
  adr/          # Architecture Decision Records
  diagramas/    # Diagramas C4, sequência e topologia (Mermaid)
Makefile        # make up / demo / down / test
```

Cada serviço em `services/` segue arquitetura hexagonal:
`src/domain` (entidades, value objects, portas), `src/application` (casos
de uso), `src/infrastructure` (adapters: FastAPI, DynamoDB/SQS/EventBridge
via boto3, repositórios em memória para testes/demo).

## Decisões de arquitetura (ADRs)

| ADR | Decisão |
|---|---|
| [01](docs/adr/01-ddd.md) | DDD: bounded contexts, agregados e linguagem ubíqua |
| [02](docs/adr/02-outbox-relay.md) | Entrega confiável de eventos via Transactional Outbox + relay por polling |
| [03](docs/adr/03-consistencia-limite.md) | Consistência do agregado Limite sob concorrência (`TransactWriteItems`) |
| [04](docs/adr/04-saga-autorizacao-limite.md) | Saga leve + idempotência + sweeper entre Autorização e Limite |
| [05](docs/adr/05-runtime-eks.md) | Runtime: EKS em produção, kind localmente |
| [06](docs/adr/06-persistencia-e-valores-monetarios.md) | Persistência (database-per-service) e representação de valores monetários |

Diagramas de arquitetura (C4, sequência, fluxo de evento, topologia de
deployment): ver [docs/diagramas/](docs/diagramas/README.md).

## Como rodar

Pré-requisitos: `docker`, `kind`, `kubectl`, `helm`, `terraform`, `python3`.

```bash
make up     # cria o cluster kind, instala KEDA, builda e sobe os 4 serviços + LocalStack, aplica o Terraform
make demo   # seed de limite -> autoriza transação -> estorna -> mostra logs do pipeline de eventos
make down   # destrói todo o ambiente (terraform destroy + kind delete)
```

`make test` roda a suíte de testes unitários dos 4 serviços (requer um
`.venv` por serviço — ver seção "Testes" abaixo).

> **Nota sobre esta entrega**: o `Makefile`, os manifestos k8s e os
> módulos Terraform foram validados estaticamente nesta sessão
> (`kubectl apply --dry-run=client`, `terraform validate`, `make -n`,
> builds Docker reais com smoke tests manuais, incluindo dois containers
> — `autorizacao` e `limites` — se comunicando via HTTP real na mesma
> rede Docker). O fluxo `make up` ponta a ponta com `kind`/LocalStack não
> foi executado neste sandbox por ele ser um ambiente **compartilhado**
> com outros processos em uso (evitar consumir recursos de terceiros);
> o design foi revisado para ser consistente e executável em um ambiente
> dedicado.

## Testes

Cada serviço tem seu próprio ambiente virtual (dependências isoladas por
bounded context, sem biblioteca de domínio compartilhada — ver ADR 01):

```bash
cd services/<servico>
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

Status atual: **38/38 testes passando** (limites: 21, autorizacao: 11,
contabilizacao: 3, outbox-relay: 3).

## Principais decisões de design (resumo)

- **Outbox + relay por polling** em vez de DynamoDB Streams + EventBridge
  Pipes — mais simples e robusto de rodar/depurar no LocalStack (ADR 02).
- **`TransactWriteItems`** com condição
  `saldo_reservado + valor <= limite_total` para impedir estouro de
  limite sob concorrência (ADR 03).
- **Saga leve orientada a estado** (não coreografia) entre Autorização e
  Limite, com reserva idempotente por `id_autorizacao` e um sweeper para
  reconciliar autorizações presas em `PENDENTE` (ADR 04).
- **Idempotência de borda** via header `Idempotency-Key`: mesma chave +
  payload diferente → `422`; operação em andamento/conflito de
  concorrência → `409`.
- **Valores monetários como string** (`"150.00"`) no JSON, convertidos
  para `Decimal` internamente — evita erro de ponto flutuante (ADR 06).
- **`id_autorizacao_original`** no estorno, para rastrear a cadeia
  autorização → estorno.
- **KEDA**: `contabilizacao` escala pelo scaler nativo `aws-sqs-queue`
  (profundidade de fila); `outbox-relay` escala por um scaler
  `metrics-api` customizado (`/metrics` → `{"pendentes": N}`), pois não
  existe scaler nativo para "itens pendentes em uma GSI do DynamoDB".
- **EKS em produção** (não ECS) — justificado pelo domínio do time em
  Kubernetes/GitOps/KEDA (ADR 05).
