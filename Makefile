SHELL := /bin/bash
.DEFAULT_GOAL := help

CLUSTER_NAME := desafio-autorizacao-limites
NAMESPACE := financas
KEDA_NAMESPACE := keda
LOCALSTACK_URL := http://localhost:4566
AUTORIZACAO_URL := http://localhost:8080
TF_DIR := terraform/envs/local

.PHONY: help up down demo build-images load-images deploy-k8s install-keda wait-ready terraform-apply seed clean-images test

help: ## Lista os alvos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

test: ## Roda a suíte de testes de todos os serviços (requer .venv por serviço, ver README)
	@set -e; \
	for svc in limites autorizacao contabilizacao outbox-relay; do \
		echo ">> testes: $$svc"; \
		( cd services/$$svc && .venv/bin/python -m pytest -q ); \
	done

build-images: ## Builda as imagens Docker dos 4 serviços (tag :local)
	docker build -t limites-service:local services/limites
	docker build -t autorizacao-service:local services/autorizacao
	docker build -t contabilizacao-service:local services/contabilizacao
	docker build -t outbox-relay-service:local services/outbox-relay

load-images: build-images ## Carrega as imagens no cluster kind (sem precisar de registry)
	kind load docker-image limites-service:local --name $(CLUSTER_NAME)
	kind load docker-image autorizacao-service:local --name $(CLUSTER_NAME)
	kind load docker-image contabilizacao-service:local --name $(CLUSTER_NAME)
	kind load docker-image outbox-relay-service:local --name $(CLUSTER_NAME)

install-keda: ## Instala o KEDA via Helm (necessário para os ScaledObject)
	helm repo add kedacore https://kedacore.github.io/charts --force-update
	helm repo update kedacore
	kubectl create namespace $(KEDA_NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	helm upgrade --install keda kedacore/keda --namespace $(KEDA_NAMESPACE) --wait --timeout 3m

deploy-k8s: ## Aplica os manifestos k8s (namespace, config, serviços, KEDA ScaledObjects)
	kubectl apply -f deploy/k8s/00-namespace.yaml
	kubectl apply -f deploy/k8s/01-config.yaml
	kubectl apply -f deploy/k8s/05-localstack.yaml
	kubectl rollout status deployment/localstack -n $(NAMESPACE) --timeout=120s
	kubectl apply -f deploy/k8s/10-limites.yaml
	kubectl apply -f deploy/k8s/11-autorizacao.yaml
	kubectl apply -f deploy/k8s/20-contabilizacao.yaml
	kubectl apply -f deploy/k8s/30-outbox-relay.yaml

wait-ready: ## Espera os Deployments ficarem prontos
	kubectl rollout status deployment/limites -n $(NAMESPACE) --timeout=120s
	kubectl rollout status deployment/autorizacao -n $(NAMESPACE) --timeout=120s
	kubectl rollout status deployment/outbox-relay -n $(NAMESPACE) --timeout=120s

terraform-apply: ## Provisiona DynamoDB/SQS/EventBridge no LocalStack via Terraform
	cd $(TF_DIR) && terraform init -input=false
	cd $(TF_DIR) && terraform apply -auto-approve -var localstack_endpoint=$(LOCALSTACK_URL)

up: ## Sobe o cluster kind, LocalStack, KEDA, serviços e provisiona IaC (fluxo completo)
	kind get clusters | grep -q '^$(CLUSTER_NAME)$$' || kind create cluster --config deploy/kind/kind-config.yaml
	$(MAKE) install-keda
	$(MAKE) load-images
	$(MAKE) deploy-k8s
	$(MAKE) wait-ready
	$(MAKE) terraform-apply
	@echo ">> Ambiente pronto. Autorização disponível em $(AUTORIZACAO_URL), LocalStack em $(LOCALSTACK_URL)."
	@echo ">> Rode 'make demo' para ver o fluxo ponta a ponta."

demo: ## Seeda um contrato, autoriza uma transação, estorna, e mostra os logs do pipeline de outbox
	@set -e; \
	echo ">> seed: cadastrando limite de 1000.00 para o contrato demo-1"; \
	curl -sf -X POST $(AUTORIZACAO_URL)/internal/contratos/demo-1/limites \
		-H 'content-type: application/json' -d '{"limite_total":"1000.00"}'; echo; \
	echo ">> autorizando transacao de 150.00"; \
	RESP=$$(curl -sf -X POST $(AUTORIZACAO_URL)/v1/contratos/demo-1/autorizacoes \
		-H 'content-type: application/json' -H 'Idempotency-Key: demo-key-1' \
		-d '{"id_conta":"conta-demo","valor":"150.00","moeda":"BRL","tipo_operacao":"DEBITO"}'); \
	echo "$$RESP"; \
	ID_AUT=$$(echo "$$RESP" | python3 -c 'import sys, json; print(json.load(sys.stdin)["id_autorizacao"])'); \
	echo ">> estornando autorizacao $$ID_AUT"; \
	curl -sf -X POST $(AUTORIZACAO_URL)/v1/contratos/demo-1/autorizacoes/$$ID_AUT/estornos \
		-H 'content-type: application/json' -H 'Idempotency-Key: demo-key-estorno-1' \
		-d "{\"id_autorizacao_original\":\"$$ID_AUT\",\"valor\":\"150.00\",\"moeda\":\"BRL\"}"; echo; \
	echo ">> logs recentes do outbox-relay (publicacao do evento TransacaoAutorizada):"; \
	kubectl logs deployment/outbox-relay -n $(NAMESPACE) --tail=20 2>/dev/null || true; \
	echo ">> logs recentes da contabilizacao (consumo idempotente do evento):"; \
	kubectl logs deployment/contabilizacao -n $(NAMESPACE) --tail=20 2>/dev/null || true

clean-images: ## Remove as imagens :local construídas localmente
	-docker rmi limites-service:local autorizacao-service:local contabilizacao-service:local outbox-relay-service:local

down: ## Destroi o cluster kind (e todo o ambiente local)
	-cd $(TF_DIR) && terraform destroy -auto-approve -var localstack_endpoint=$(LOCALSTACK_URL)
	kind delete cluster --name $(CLUSTER_NAME)
	$(MAKE) clean-images
