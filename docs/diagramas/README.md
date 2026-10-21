# Diagramas de Arquitetura

Diagramas em Mermaid (renderizados nativamente em GitHub/VS Code/clientes
compatíveis com Mermaid). Cada arquivo cobre uma visão distinta do
sistema.

| Arquivo | Visão |
|---|---|
| [01-contexto-c4.md](./01-contexto-c4.md) | C4 Nível 1 (Contexto) — atores e sistemas externos |
| [02-containers-c4.md](./02-containers-c4.md) | C4 Nível 2 (Containers) — bounded contexts e bancos de dados |
| [03-sequencia-autorizacao.md](./03-sequencia-autorizacao.md) | Sequência da saga de autorização (caminho feliz + recusa) |
| [04-sequencia-estorno.md](./04-sequencia-estorno.md) | Sequência do estorno de uma autorização |
| [05-fluxo-evento-outbox.md](./05-fluxo-evento-outbox.md) | Fluxo do evento `TransacaoAutorizada` via Outbox + Relay + EventBridge |
| [06-topologia-deployment.md](./06-topologia-deployment.md) | Topologia de deployment local (kind) e produção (EKS) |
