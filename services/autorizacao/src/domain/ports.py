"""Ports (interfaces) do contexto de Autorização.

`LimiteGateway` é o port de anticorrupção (ACL) para o contexto de
Limites: em produção, o adapter concreto chama o Serviço de Limites via
HTTP/API Gateway; em testes e no `make demo` local, um adapter in-process
delega diretamente para o caso de uso do serviço de Limites, permitindo
testar a saga completa sem rede.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from .autorizacao import Autorizacao
from .idempotencia import RegistroIdempotencia
from .outbox import RegistroOutbox
from .value_objects import Money, TipoOperacao


class AutorizacaoRepository(ABC):
    @abstractmethod
    def buscar(self, id_autorizacao: str) -> Optional[Autorizacao]:
        ...

    @abstractmethod
    def salvar(self, autorizacao: Autorizacao) -> None:
        ...

    @abstractmethod
    def listar_pendentes_antes_de(self, limite_tempo: datetime) -> list[Autorizacao]:
        """Usado pelo sweeper (ver ADR 04) para reconciliar autorizações
        presas em PENDENTE há mais tempo que o timeout configurado."""

    def salvar_com_evento(
        self,
        autorizacao: Autorizacao,
        registro_outbox: Optional[RegistroOutbox],
        outbox_repository: Optional["OutboxRepository"] = None,
    ) -> None:
        """Grava a autorização e, se houver, o evento de outbox
        correspondente. Implementação padrão (não atômica entre as duas
        escritas) usada pelo adapter em memória — adequada porque o
        processo não "morre no meio" de duas chamadas Python síncronas
        na prática de testes/demo local. O adapter DynamoDB sobrescreve
        este método com uma única `TransactWriteItems` cruzando as
        tabelas `autorizacoes` e `autorizacao-outbox`, fechando o gap
        descrito na ADR 02 (nunca existe decisão persistida sem o evento
        correspondente, nem o inverso)."""
        self.salvar(autorizacao)
        if registro_outbox is not None and outbox_repository is not None:
            outbox_repository.salvar(registro_outbox)


class IdempotenciaRepository(ABC):
    @abstractmethod
    def buscar(self, idempotency_key: str) -> Optional[RegistroIdempotencia]:
        ...

    @abstractmethod
    def salvar(self, registro: RegistroIdempotencia) -> None:
        ...


class LimiteGatewayResultado:
    """DTO de resposta do gateway de Limites, agnóstico de transporte."""

    def __init__(self, saldo_reservado: Money):
        self.saldo_reservado = saldo_reservado


class OutboxRepository(ABC):
    """Port de persistência da tabela de outbox (ver ADR 02). O adapter
    em memória é usado em testes/demo; em produção, o adapter concreto
    grava na mesma `TransactWriteItems` do agregado de Autorização."""

    @abstractmethod
    def salvar(self, registro: "RegistroOutbox") -> None:
        ...

    @abstractmethod
    def listar_pendentes(self, limite: int = 50) -> list["RegistroOutbox"]:
        ...


class LimiteGateway(ABC):
    @abstractmethod
    def aplicar_operacao(
        self,
        id_contrato: str,
        id_autorizacao: str,
        valor: Money,
        tipo_operacao: TipoOperacao,
    ) -> LimiteGatewayResultado:
        """Solicita a reserva/liberação de limite. Deve levantar
        `LimiteInsuficienteError` (do domínio de Autorização) em caso de
        recusa de negócio, ou uma exceção de indeterminação (timeout/5xx)
        que o caso de uso trata deixando a autorização `PENDENTE`."""

    @abstractmethod
    def consultar_reserva(
        self, id_contrato: str, id_autorizacao: str
    ) -> Optional[LimiteGatewayResultado]:
        """Usado pelo sweeper (ADR 04) para descobrir, de forma
        idempotente, se uma reserva foi efetivada do lado do Serviço de
        Limites. Retorna `None` se a reserva nunca existiu."""
