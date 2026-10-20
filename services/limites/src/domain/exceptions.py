"""Exceções de domínio do contexto de Limites.

Cada exceção mapeia para uma semântica HTTP específica na camada de API
(ver contracts/openapi.yaml), mas o domínio não conhece HTTP — o mapeamento
é responsabilidade do adapter de entrada (ver services/limites/src/infrastructure).
"""


class LimiteDomainError(Exception):
    """Classe base para erros de domínio do contexto de Limites."""


class ContratoNaoEncontradoError(LimiteDomainError):
    """O contrato informado não possui um limite cadastrado."""


class LimiteInsuficienteError(LimiteDomainError):
    """A operação excederia o limite total disponível do contrato.

    Mapeia para HTTP 402 Payment Required.
    """


class OperacaoInvalidaError(LimiteDomainError):
    """A operação viola uma invariante de domínio que não é "limite
    insuficiente" (ex: estorno maior que o saldo reservado existente).

    Mapeia para HTTP 422 Unprocessable Entity.
    """


class TipoOperacaoDesconhecidoError(LimiteDomainError):
    """Não existe política registrada para o tipo de operação informado."""
