"""Exceções de domínio do contexto de Contabilização."""


class ContabilizacaoDomainError(Exception):
    """Classe base para erros do contexto de Contabilização."""


class EventoInvalidoError(ContabilizacaoDomainError):
    """O envelope do evento recebido não contém os campos obrigatórios do
    schema `contracts/events/TransacaoAutorizada.v1.schema.json`."""
