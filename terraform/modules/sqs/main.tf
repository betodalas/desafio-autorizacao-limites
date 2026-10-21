variable "tags" {
  type    = map(string)
  default = {}
}

# Dead-letter queue: mensagens que falharem `max_receive_count` vezes no
# consumo por Contabilização vão parar aqui para investigação manual.
resource "aws_sqs_queue" "contabilizacao_dlq" {
  name = "contabilizacao-dlq"
  tags = var.tags
}

# Fila consumida por Contabilização (ver ADR 02). O KEDA escala o
# Deployment de Contabilização usando o scaler nativo `aws-sqs-queue`
# contra a profundidade desta fila (ver deploy/k8s/20-contabilizacao.yaml).
resource "aws_sqs_queue" "contabilizacao" {
  name                       = "contabilizacao"
  visibility_timeout_seconds = 30

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.contabilizacao_dlq.arn
    maxReceiveCount     = 5
  })

  tags = var.tags
}

output "fila_contabilizacao_url" {
  value = aws_sqs_queue.contabilizacao.url
}

output "fila_contabilizacao_arn" {
  value = aws_sqs_queue.contabilizacao.arn
}

output "fila_contabilizacao_dlq_url" {
  value = aws_sqs_queue.contabilizacao_dlq.url
}
