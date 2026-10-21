variable "tags" {
  type    = map(string)
  default = {}
}

variable "fila_contabilizacao_arn" {
  description = "ARN da fila SQS de destino para o evento TransacaoAutorizada."
  type        = string
}

variable "fila_contabilizacao_url" {
  description = "URL da fila SQS de destino (necessária para a policy)."
  type        = string
}

# Bus dedicado do domínio financeiro (ver ADR 02 e 05). O outbox-relay
# publica aqui via `put_events`.
resource "aws_cloudwatch_event_bus" "financas" {
  name = "financas-eventos"
  tags = var.tags
}

# Roteia o evento de domínio `TransacaoAutorizada` (publicado pelo
# outbox-relay a partir da outbox de Autorização) para a fila consumida
# por Contabilização.
resource "aws_cloudwatch_event_rule" "transacao_autorizada" {
  name           = "transacao-autorizada-para-contabilizacao"
  event_bus_name = aws_cloudwatch_event_bus.financas.name

  event_pattern = jsonencode({
    source      = ["autorizacao"]
    detail-type = ["TransacaoAutorizada"]
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "para_contabilizacao" {
  rule           = aws_cloudwatch_event_rule.transacao_autorizada.name
  event_bus_name = aws_cloudwatch_event_bus.financas.name
  arn            = var.fila_contabilizacao_arn
}

# Permite que o EventBridge entregue mensagens na fila SQS de
# Contabilização.
resource "aws_sqs_queue_policy" "permite_eventbridge" {
  queue_url = var.fila_contabilizacao_url

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PermiteEventBridgePublicarNaFila"
        Effect    = "Allow"
        Principal = { Service = "events.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = var.fila_contabilizacao_arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_cloudwatch_event_rule.transacao_autorizada.arn
          }
        }
      }
    ]
  })
}

output "nome_bus" {
  value = aws_cloudwatch_event_bus.financas.name
}
