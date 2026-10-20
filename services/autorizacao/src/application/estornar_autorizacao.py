"""Caso de uso: estornar (total ou parcialmente) uma autorização aprovada.

Segue o mesmo padrão de saga e idempotência de `autorizar_transacao.py`,
mas valida a autorização original e delega ao gateway uma operação do
tipo ESTORNO, que libera saldo previamente reservado (ver ADR 03/04).
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Optional

from ..domain import (
    AutorizacaoOriginalInvalidaError,
    AutorizacaoRepository,
    Autorizacao,
    IdempotenciaRepository,
    LimiteGateway,
    LimiteGatewayIndeterminadoError,
    LimiteOperacaoInvalidaError,
    Money,
    OperacaoEmAndamentoError,
    PayloadDivergenteError,
    RegistroIdempotencia,
    StatusAutorizacao,
    StatusIdempotencia,
    TipoOperacao,
    calcular_hash_payload,
)
from .autorizar_transacao import AutorizacaoResultado

_NAMESPACE_ESTORNO = uuid.UUID("b5f4c2b1-0c2e-4f2b-9c1b-3a7d2e0f8b11")


@dataclass(frozen=True)
class EstornarAutorizacaoComando:
    idempotency_key: str
    id_contrato: str
    id_autorizacao_original: str
    valor: str
    moeda: str


class EstornarAutorizacaoUseCase:
    def __init__(
        self,
        autorizacao_repository: AutorizacaoRepository,
        idempotencia_repository: IdempotenciaRepository,
        limite_gateway: LimiteGateway,
    ):
        self._autorizacoes = autorizacao_repository
        self._idempotencias = idempotencia_repository
        self._limite_gateway = limite_gateway

    def executar(self, comando: EstornarAutorizacaoComando) -> AutorizacaoResultado:
        payload = asdict(comando)
        payload.pop("idempotency_key")
        hash_payload = calcular_hash_payload(payload)

        registro_existente = self._idempotencias.buscar(comando.idempotency_key)
        if registro_existente is not None:
            if registro_existente.hash_payload != hash_payload:
                raise PayloadDivergenteError(
                    "Idempotency-Key já utilizada com um payload diferente"
                )
            if registro_existente.status == StatusIdempotencia.EM_ANDAMENTO:
                raise OperacaoEmAndamentoError(
                    "Requisição de estorno com esta Idempotency-Key ainda está em andamento"
                )
            resultado = dict(registro_existente.resultado or {})
            resultado["repetida"] = True
            return AutorizacaoResultado(**resultado)

        original = self._autorizacoes.buscar(comando.id_autorizacao_original)
        if original is None or original.status != StatusAutorizacao.APROVADA:
            raise AutorizacaoOriginalInvalidaError(
                f"Autorização original {comando.id_autorizacao_original!r} não "
                "existe ou não está aprovada"
            )
        valor = Money.from_str(comando.valor)
        valor.exige_positivo()
        if original.saldo_reservado is not None and valor > original.saldo_reservado:
            raise AutorizacaoOriginalInvalidaError(
                "Valor de estorno excede o saldo reservado pela autorização original"
            )

        id_autorizacao = str(uuid.uuid5(_NAMESPACE_ESTORNO, comando.idempotency_key))
        estorno = Autorizacao.nova_pendente(
            id_autorizacao=id_autorizacao,
            id_contrato=comando.id_contrato,
            id_conta=original.id_conta,
            valor=valor,
            moeda=comando.moeda,
            tipo_operacao=TipoOperacao.ESTORNO,
            id_autorizacao_original=original.id_autorizacao,
        )
        self._autorizacoes.salvar(estorno)
        registro = RegistroIdempotencia.iniciar(comando.idempotency_key, hash_payload, id_autorizacao)
        self._idempotencias.salvar(registro)

        try:
            resultado_gateway = self._limite_gateway.aplicar_operacao(
                id_contrato=comando.id_contrato,
                id_autorizacao=id_autorizacao,
                valor=valor,
                tipo_operacao=TipoOperacao.ESTORNO,
            )
        except LimiteOperacaoInvalidaError:
            estorno.recusar()
            self._autorizacoes.salvar(estorno)
            raise
        except LimiteGatewayIndeterminadoError as exc:
            raise OperacaoEmAndamentoError(
                "Falha indeterminada ao liberar limite; tente novamente com a mesma Idempotency-Key"
            ) from exc

        estorno.aprovar(resultado_gateway.saldo_reservado)
        self._autorizacoes.salvar(estorno)
        resultado = AutorizacaoResultado.de_autorizacao(estorno)
        registro.concluir(asdict(resultado))
        self._idempotencias.salvar(registro)
        return resultado
