variable "tags" {
  description = "Tags comuns aplicadas às tabelas."
  type        = map(string)
  default     = {}
}

# Tabela do agregado Limite (ver ADR 01 e ADR 03). Modelo single-table:
# o item do Limite usa pk = "CONTRATO#<id_contrato>"; cada reserva
# idempotente por autorização usa pk = "CONTRATO#<id_contrato>#RESERVA#<id_autorizacao>",
# permitindo que a condição `saldo_reservado + valor <= limite_total` e a
# checagem de idempotência da reserva sejam resolvidas na mesma
# `TransactWriteItems`.
resource "aws_dynamodb_table" "limites" {
  name         = "limites"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  tags = var.tags
}

# Tabela do agregado Autorizacao (ver ADR 04). Chave: id_autorizacao.
resource "aws_dynamodb_table" "autorizacoes" {
  name         = "autorizacoes"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id_autorizacao"

  attribute {
    name = "id_autorizacao"
    type = "S"
  }

  tags = var.tags
}

# Registros de idempotência de requisições (`Idempotency-Key`), ver
# contracts/openapi.yaml e ADR 04.
resource "aws_dynamodb_table" "idempotencia" {
  name         = "idempotencia"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "idempotency_key"

  attribute {
    name = "idempotency_key"
    type = "S"
  }

  tags = var.tags
}

# Tabela da outbox do Serviço de Autorização (ver ADR 02). GSI
# `status-index` permite ao outbox-relay consultar eficientemente os
# registros PENDENTE sem fazer scan completo da tabela.
resource "aws_dynamodb_table" "outbox" {
  name         = "autorizacao-outbox"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "event_id"

  attribute {
    name = "event_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "criado_em"
    type = "S"
  }

  global_secondary_index {
    name            = "status-index"
    hash_key        = "status"
    range_key       = "criado_em"
    projection_type = "ALL"
  }

  tags = var.tags
}

output "tabela_limites" {
  value = aws_dynamodb_table.limites.name
}

output "tabela_autorizacoes" {
  value = aws_dynamodb_table.autorizacoes.name
}

output "tabela_idempotencia" {
  value = aws_dynamodb_table.idempotencia.name
}

output "tabela_outbox" {
  value = aws_dynamodb_table.outbox.name
}
