terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Provider apontado para o LocalStack (ver ADR 05: em produção, este
# `envs/local` não existiria — haveria um `envs/prod` sem os overrides de
# endpoint/credenciais abaixo, usando a AWS real e um backend remoto de
# state).
provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    dynamodb = var.localstack_endpoint
    sqs      = var.localstack_endpoint
    events   = var.localstack_endpoint
  }
}

variable "localstack_endpoint" {
  description = "Endpoint do LocalStack. Via `make up`, aponta para o NodePort exposto pelo kind (http://localhost:4566)."
  type        = string
  default     = "http://localhost:4566"
}

locals {
  tags = {
    ambiente = "local"
    projeto  = "desafio-autorizacao-limites"
  }
}

module "dynamodb" {
  source = "../../modules/dynamodb"
  tags   = local.tags
}

module "sqs" {
  source = "../../modules/sqs"
  tags   = local.tags
}

module "eventbridge" {
  source                  = "../../modules/eventbridge"
  tags                    = local.tags
  fila_contabilizacao_arn = module.sqs.fila_contabilizacao_arn
  fila_contabilizacao_url = module.sqs.fila_contabilizacao_url
}

output "fila_contabilizacao_url" {
  value = module.sqs.fila_contabilizacao_url
}

output "tabela_outbox" {
  value = module.dynamodb.tabela_outbox
}

output "nome_bus" {
  value = module.eventbridge.nome_bus
}
