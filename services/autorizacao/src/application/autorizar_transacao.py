"""Caso de uso: autorizar uma transação financeira.

Orquestra a saga leve descrita na ADR 04: cria a autorização PENDENTE,
registra idempotência, solicita a reserva de limite via `LimiteGateway` e
resolve o estado final (APROVADA/RECUSADA), propagando as exceções que a
camada de API traduz nos códigos HTTP do contrato (402/409/422).
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any, Optional

from ..domain import (
    Autorizacao,
    AutorizacaoRepository,
    IdempotenciaRepository,
    LimiteGateway,
    LimiteGatewayIndeterminadoError,
    LimiteInsuficienteError,
    Money,
    OperacaoEmAndamentoError,
    OutboxRepository,
    PayloadDivergenteError,
    RegistroIdempotencia,
    RegistroOutbox,
    StatusAutorizacao,
    StatusIdempotencia,
    TipoOperacao,
    TransacaoAutorizada,
    calcular_hash_payload,
)

_NAMESPACE_IDEMPOTENCIA = uuid.UUID("a4f3b1a0-9b1d-4e1a-8b0a-2f6c1d9e7a00")


@dataclass(frozen=True)
class AutorizarTransacaoComando:
    idempotency_key: str
    id_contrato: str
    id_conta: str
    valor: str
    moeda: str
    tipo_operacao: str
    id_estabelecimento: Optional[str] = None


@dataclass(frozen=True)
class AutorizacaoResultado:
    id_autorizacao: str
    id_contrato: str
    status: str
    valor: str
    saldo_reservado: Optional[str]
    criado_em: str
    repetida: bool = False

    @classmethod
    def de_autorizacao(cls, autorizacao: Autorizacao, repetida: bool = False) -> "AutorizacaoResultado":
        return cls(
            id_autorizacao=autorizacao.id_autorizacao,
            id_contrato=autorizacao.id_contrato,
            status=autorizacao.status.value,
            valor=str(autorizacao.valor),
            saldo_reservado=(
                str(autorizacao.saldo_reservado)
                if autorizacao.saldo_reservado is not None
                else None
            ),
            criado_em=autorizacao.criado_em.isoformat(),
            repetida=repetida,
        )


class AutorizarTransacaoUseCase:
    def __init__(
        self,
        autorizacao_repository: AutorizacaoRepository,
        idempotencia_repository: IdempotenciaRepository,
        limite_gateway: LimiteGateway,
        outbox_repository: Optional[OutboxRepository] = None,
    ):
        self._autorizacoes = autorizacao_repository
        self._idempotencias = idempotencia_repository
        self._limite_gateway = limite_gateway
        self._outbox = outbox_repository

    def executar(self, comando: AutorizarTransacaoComando) -> AutorizacaoResultado:
        payload = asdict(comando)
        payload.pop("idempotency_key")
        hash_payload = calcular_hash_payload(payload)

        registro_existente = self._idempotencias.buscar(comando.idempotency_key)
        if registro_existente is not None:
            return self._resolver_reenvio(registro_existente, hash_payload)

        id_autorizacao = str(uuid.uuid5(_NAMESPACE_IDEMPOTENCIA, comando.idempotency_key))
        valor = Money.from_str(comando.valor)
        tipo_operacao = TipoOperacao(comando.tipo_operacao)

        autorizacao = Autorizacao.nova_pendente(
            id_autorizacao=id_autorizacao,
            id_contrato=comando.id_contrato,
            id_conta=comando.id_conta,
            valor=valor,
            moeda=comando.moeda,
            tipo_operacao=tipo_operacao,
        )
        self._autorizacoes.salvar(autorizacao)
        registro = RegistroIdempotencia.iniciar(
            comando.idempotency_key, hash_payload, id_autorizacao
        )
        self._idempotencias.salvar(registro)

        try:
            resultado_gateway = self._limite_gateway.aplicar_operacao(
                id_contrato=comando.id_contrato,
                id_autorizacao=id_autorizacao,
                valor=valor,
                tipo_operacao=tipo_operacao,
            )
        except LimiteInsuficienteError:
            autorizacao.recusar()
            self._autorizacoes.salvar(autorizacao)
            resultado = AutorizacaoResultado.de_autorizacao(autorizacao)
            registro.concluir(asdict(resultado))
            self._idempotencias.salvar(registro)
            raise
        except LimiteGatewayIndeterminadoError as exc:
            # Autorização permanece PENDENTE; idempotência permanece
            # EM_ANDAMENTO. O sweeper (ADR 04) reconcilia posteriormente.
            raise OperacaoEmAndamentoError(
                "Falha indeterminada ao reservar limite; tente novamente "
                "com a mesma Idempotency-Key"
            ) from exc

        autorizacao.aprovar(resultado_gateway.saldo_reservado)
        registro_outbox = self._montar_registro_outbox(autorizacao, comando.idempotency_key)
        self._autorizacoes.salvar_com_evento(autorizacao, registro_outbox, self._outbox)
        resultado = AutorizacaoResultado.de_autorizacao(autorizacao)
        registro.concluir(asdict(resultado))
        self._idempotencias.salvar(registro)
        return resultado

    def _montar_registro_outbox(
        self, autorizacao: Autorizacao, correlation_id: str
    ) -> Optional[RegistroOutbox]:
        """Monta o registro de outbox do evento `TransacaoAutorizada` (ver
        ADR 02), gravado junto com a autorização numa única escrita
        atômica em `salvar_com_evento`. Se `outbox_repository` não foi
        fornecido (ex.: testes focados na saga), não há o que montar."""
        if self._outbox is None:
            return None
        evento = TransacaoAutorizada.agora(
            id_autorizacao=autorizacao.id_autorizacao,
            id_contrato=autorizacao.id_contrato,
            valor=autorizacao.valor,
            saldo_reservado=autorizacao.saldo_reservado,
            correlation_id=correlation_id,
        )
        return RegistroOutbox.para(evento)

    def _resolver_reenvio(
        self, registro: RegistroIdempotencia, hash_payload: str
    ) -> AutorizacaoResultado:
        if registro.hash_payload != hash_payload:
            raise PayloadDivergenteError(
                "Idempotency-Key já utilizada com um payload diferente"
            )
        if registro.status == StatusIdempotencia.EM_ANDAMENTO:
            raise OperacaoEmAndamentoError(
                "Requisição com esta Idempotency-Key ainda está em andamento"
            )

        resultado_original = dict(registro.resultado or {})
        resultado_original["repetida"] = True
        resultado = AutorizacaoResultado(**resultado_original)
        if resultado.status == StatusAutorizacao.RECUSADA.value:
            raise LimiteInsuficienteError(
                "Reenvio de autorização previamente recusada por limite insuficiente"
            )
        return resultado
