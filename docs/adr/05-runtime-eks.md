# ADR 05 — Runtime de compute: EKS (produção) e Kubernetes local (kind) para o desafio

## Status
Aceito

## Contexto
O requisito pede para justificar a escolha entre AWS Lambda, Amazon
ECS/Fargate ou Amazon EKS, considerando o SLA de ~5.000 TPS de pico e
latência de autorização em tempo real, além de permitir demonstração local
via Docker/kind.

## Decisão
Escolhemos **Amazon EKS** como runtime de produção, com **KEDA** para
autoscaling orientado a eventos (filas SQS, fila de outbox pendente, e
métricas customizas), e replicamos a topologia localmente com **kind**
(Kubernetes in Docker) + **LocalStack** para os serviços AWS.

Justificativa frente às alternativas:

- **AWS Lambda:** adequado para picos muito elásticos e cobrança por
  invocação, mas: (a) cold start pode violar SLA de latência em p99 para
  autorização síncrona sob tráfego sustentado de ~5.000 TPS; (b) conexões
  persistentes para pool de conexões / warm paths são mais difíceis de
  gerenciar em Lambda; (c) o time (conforme contexto já definido com o
  stakeholder) tem domínio operacional consolidado em Kubernetes/GitOps/
  KEDA, o que reduz risco de entrega e operação comparado a adotar um
  novo paradigma serverless para um serviço core de missão crítica.
- **ECS/Fargate:** reduziria a complexidade de operar um control plane
  Kubernetes, mas o time não teria o mesmo ecossistema de autoscaling
  orientado a eventos (KEDA) nem GitOps já maduro usado em outras
  plataformas do banco — trocaria uma componente dominada (EKS) por uma
  nova a aprender, sem ganho líquido claro para este domínio.
- **EKS (escolhido):** reaproveita GitOps, observability stack, políticas
  de rede (NetworkPolicy/Service Mesh) e autoscaling (KEDA) já
  padronizados no time; permite paridade quase total entre ambiente local
  (kind) e produção, o que é valioso tanto para a demonstração do desafio
  quanto para reduzir divergência dev/prod no dia a dia.

## Consequências
- Cada serviço (`autorizacao`, `limites`, `contabilizacao`,
  `outbox-relay`) é empacotado como imagem de container e implantado como
  Deployment + Service no Kubernetes (`deploy/k8s`), com HPA/KEDA
  `ScaledObject` para escalar conforme TPS (autorização, via métrica
  customizada ou fila) e tamanho de fila (outbox-relay).
- Para rodar localmente, o `Makefile` provisiona um cluster `kind`, sobe o
  LocalStack (DynamoDB, SQS, EventBridge) e aplica os manifests em
  `deploy/kind`, permitindo `make up && make demo && make down` fim-a-fim
  sem conta AWS real.
- Em produção, recomenda-se Karpenter/Cluster Autoscaler para o
  autoscaling de nós, complementando o KEDA (que escala pods).
