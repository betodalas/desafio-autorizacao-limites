"""Exceções de domínio e de aplicação do contexto de Autorização.

Mapeiam diretamente para a semântica HTTP do contrato de API
(contracts/openapi.yaml):

- LimiteInsuficienteError      -> 402 Payment Required
- OperacaoEmAndamentoError     -> 409 Conflict
- PayloadDivergenteError       -> 422 Unprocessable Entity
- AutorizacaoOriginalInvalidaError -> 422 Unprocessable Entity
"""


class AutorizacaoDomainError(Exception):
    """Classe base para erros do contexto de Autorização."""


class LimiteInsuficienteError(AutorizacaoDomainError):
    """A reserva de limite foi recusada por saldo insuficiente."""


class OperacaoEmAndamentoError(AutorizacaoDomainError):
    """A autorização para esta Idempotency-Key ainda está sendo
    processada (saga pendente) — cliente deve tentar novamente."""


class PayloadDivergenteError(AutorizacaoDomainError):
    """A Idempotency-Key foi reutilizada com um payload diferente do
    originalmente processado."""


class AutorizacaoOriginalInvalidaError(AutorizacaoDomainError):
    """A autorização original referenciada por um estorno não existe, não
    está aprovada, ou o valor do estorno excede o reservado."""


class LimiteGatewayIndeterminadoError(AutorizacaoDomainError):
    """A chamada ao Serviço de Limites falhou de forma indeterminada
    (timeout, erro 5xx) — não se sabe se a reserva foi efetivada do outro
    lado. A autorização permanece PENDENTE e cabe ao sweeper (ADR 04)
    reconciliar o estado posteriormente."""


class LimiteOperacaoInvalidaError(AutorizacaoDomainError):
    """O Serviço de Limites recusou a operação por violar uma invariante
    que não é "limite insuficiente" (ex: estorno maior que o reservado)."""
