# Topologia de Deployment — Local (kind) vs. Produção (EKS)

## Local (kind + LocalStack)

```mermaid
graph TB
    subgraph Host["Host (make up/demo)"]
        TF[Terraform<br/>envs/local]
        CURL[curl / make demo]
    end

    subgraph Kind["Cluster kind: desafio-autorizacao-limites"]
        subgraph NS["namespace: financas"]
            LS[localstack<br/>Deployment+Service<br/>NodePort 30566]
            LIM[limites<br/>Deployment+Service]
            AUT[autorizacao<br/>Deployment+Service<br/>NodePort 30080]
            CTB[contabilizacao<br/>Deployment]
            REL[outbox-relay<br/>Deployment+Service :9090]
        end
        subgraph NSKEDA["namespace: keda"]
            KEDA[KEDA operator<br/>+ metrics-api scaler]
        end
    end

    CURL -->|localhost:8080| AUT
    TF -->|localhost:4566| LS
    AUT -->|HTTP interno| LIM
    AUT -->|TransactWriteItems| LS
    LIM -->|TransactWriteItems| LS
    REL -->|lê GSI status-index| LS
    REL -->|put_events| LS
    LS -->|SQS: fila contabilizacao| CTB
    KEDA -.->|aws-sqs-queue scaler| CTB
    KEDA -.->|metrics-api scaler /metrics| REL
```

## Produção (EKS)

```mermaid
graph TB
    subgraph EKS["Cluster EKS"]
        subgraph NSPROD["namespace: financas"]
            LIMp[limites<br/>Deployment+Service]
            AUTp[autorizacao<br/>Deployment+Service]
            CTBp[contabilizacao<br/>Deployment]
            RELp[outbox-relay<br/>Deployment+Service]
        end
        KEDAp[KEDA operator]
    end

    subgraph AWS["AWS gerenciada"]
        APIGW[API Gateway<br/>REST — contracts/openapi.yaml]
        DDB[(DynamoDB:<br/>limites, autorizacoes,<br/>idempotencia, outbox)]
        EB[EventBridge:<br/>financas-eventos]
        SQSp[(SQS: contabilizacao + DLQ)]
    end

    APIGW --> AUTp
    AUTp -->|HTTP interno, via Service Mesh/ClusterIP| LIMp
    AUTp -->|IRSA| DDB
    LIMp -->|IRSA| DDB
    RELp -->|IRSA| DDB
    RELp -->|IRSA| EB
    EB --> SQSp
    SQSp --> CTBp
    KEDAp -.->|aws-sqs-queue| CTBp
    KEDAp -.->|metrics-api| RELp
```

## Notas

- A **única diferença estrutural** entre local e produção é a origem do DynamoDB/SQS/EventBridge: LocalStack (containerizado, dentro do próprio cluster kind) vs. AWS real. Os manifestos k8s dos 4 serviços (`deploy/k8s/10-*.yaml` a `30-*.yaml`) são os mesmos nos dois ambientes — apenas `ConfigMap`/`Secret` de endpoint/credenciais mudam (ver ADR 05).
- Em produção, autenticação AWS usa **IRSA** (IAM Roles for Service Accounts) em vez do `Secret aws-local-credentials` fake usado localmente.
- Em produção, o tráfego externo entra via **API Gateway REST** (não exposto diretamente pelo k8s), que roteia para o Service `autorizacao` via um NLB/Ingress — a API local usa NodePort apenas para simplificar o `make demo`.
- A escolha de **EKS em vez de ECS** está documentada na ADR 05, com a justificativa central de domínio do time em Kubernetes/GitOps/KEDA.
