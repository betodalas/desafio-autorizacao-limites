"""Adapter de entrada HTTP (FastAPI) do Serviço de Autorização.

Implementa os dois endpoints descritos em `contracts/openapi.yaml`:

- POST /v1/contratos/{id_contrato}/autorizacoes
- POST /v1/contratos/{id_contrato}/autorizacoes/{id_autorizacao}/estornos

Traduz exceções de domínio/aplicação para HTTP (RFC 7807 Problem Details)
conforme o contrato, e usa `Idempotency-Key` como cabeçalho obrigatório.

Para rodar localmente no mesmo processo (`make demo` fora de containers)
este app usa o `InProcessLimiteGateway`, que chama o domínio de Limites
diretamente no mesmo processo. Quando a variável de ambiente
`LIMITES_SERVICE_URL` está definida (caso de containers/k8s separados —
ver `deploy/k8s/`), usa o `HttpLimiteGateway` real, que fala HTTP com o
Serviço de Limites (em produção, atrás do API Gateway — ver ADR 05).
"""
from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any, Optional

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..application import (
    AutorizacaoResultado,
    AutorizarTransacaoComando,
    AutorizarTransacaoUseCase,
    EstornarAutorizacaoComando,
    EstornarAutorizacaoUseCase,
)
from ..domain import (
    AutorizacaoOriginalInvalidaError,
    LimiteGatewayIndeterminadoError,
    LimiteInsuficienteError,
    LimiteOperacaoInvalidaError,
    OperacaoEmAndamentoError,
    PayloadDivergenteError,
    ValorInvalidoError,
)
from .memory_repository import (
    InMemoryAutorizacaoRepository,
    InMemoryIdempotenciaRepository,
    InMemoryOutboxRepository,
)


def _construir_gateway():
    """Escolhe o adapter de `LimiteGateway` conforme o ambiente: HTTP real
    quando `LIMITES_SERVICE_URL` está configurada (containers/k8s
    separados), ou in-process para `make demo` no mesmo processo."""
    if os.environ.get("LIMITES_SERVICE_URL"):
        from .http_limite_gateway import HttpLimiteGateway

        return HttpLimiteGateway()
    from .limite_gateway_in_process import InProcessLimiteGateway

    return InProcessLimiteGateway()


def _construir_repositorios():
    """Escolhe os adapters de persistência conforme o ambiente: DynamoDB
    real quando `AWS_ENDPOINT_URL` está configurada (k8s contra
    LocalStack/AWS, ver `deploy/k8s/01-config.yaml`), ou em memória para
    testes e `make demo` local sem containers."""
    if os.environ.get("AWS_ENDPOINT_URL"):
        from .dynamodb_repository import (
            DynamoDbAutorizacaoRepository,
            DynamoDbIdempotenciaRepository,
            DynamoDbOutboxRepository,
        )

        return (
            DynamoDbAutorizacaoRepository(),
            DynamoDbIdempotenciaRepository(),
            DynamoDbOutboxRepository(),
        )
    return (
        InMemoryAutorizacaoRepository(),
        InMemoryIdempotenciaRepository(),
        InMemoryOutboxRepository(),
    )


app = FastAPI(
    title="Serviço de Autorização de Transações",
    version="1.0",
    description="Ver contracts/openapi.yaml para o contrato público completo.",
)

_autorizacoes, _idempotencias, _outbox = _construir_repositorios()
_gateway = _construir_gateway()
_autorizar = AutorizarTransacaoUseCase(_autorizacoes, _idempotencias, _gateway, _outbox)
_estornar = EstornarAutorizacaoUseCase(_autorizacoes, _idempotencias, _gateway, _outbox)

_PROBLEM_TYPE = "https://api.itau.com.br/problems"


class AutorizacaoRequest(BaseModel):
    id_conta: str
    valor: str
    moeda: str
    tipo_operacao: str
    id_estabelecimento: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class EstornoRequest(BaseModel):
    id_autorizacao_original: str
    valor: str
    moeda: str
    metadata: Optional[dict[str, Any]] = None


def _problem(status: int, titulo: str, detalhe: str, correlation_id: Optional[str]) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"{_PROBLEM_TYPE}/{titulo.lower().replace(' ', '-')}",
        "title": titulo,
        "status": status,
        "detail": detalhe,
    }
    if correlation_id:
        body["correlation_id"] = correlation_id
    return JSONResponse(status_code=status, content=body, media_type="application/problem+json")


@app.exception_handler(LimiteInsuficienteError)
async def _handle_limite_insuficiente(request: Request, exc: LimiteInsuficienteError):
    return _problem(402, "Limite insuficiente", str(exc), request.headers.get("X-Correlation-Id"))


@app.exception_handler(OperacaoEmAndamentoError)
async def _handle_operacao_em_andamento(request: Request, exc: OperacaoEmAndamentoError):
    return _problem(409, "Conflito de concorrência", str(exc), request.headers.get("X-Correlation-Id"))


@app.exception_handler(PayloadDivergenteError)
async def _handle_payload_divergente(request: Request, exc: PayloadDivergenteError):
    return _problem(422, "Payload divergente", str(exc), request.headers.get("X-Correlation-Id"))


@app.exception_handler(AutorizacaoOriginalInvalidaError)
async def _handle_autorizacao_original_invalida(request: Request, exc: AutorizacaoOriginalInvalidaError):
    return _problem(422, "Autorização original inválida", str(exc), request.headers.get("X-Correlation-Id"))


@app.exception_handler(LimiteOperacaoInvalidaError)
async def _handle_limite_operacao_invalida(request: Request, exc: LimiteOperacaoInvalidaError):
    return _problem(422, "Operação de limite inválida", str(exc), request.headers.get("X-Correlation-Id"))


@app.exception_handler(ValorInvalidoError)
async def _handle_valor_invalido(request: Request, exc: ValorInvalidoError):
    return _problem(422, "Valor inválido", str(exc), request.headers.get("X-Correlation-Id"))


@app.exception_handler(LimiteGatewayIndeterminadoError)
async def _handle_gateway_indeterminado(request: Request, exc: LimiteGatewayIndeterminadoError):
    return _problem(503, "Serviço de Limites indisponível", str(exc), request.headers.get("X-Correlation-Id"))


def _responder(resultado: AutorizacaoResultado) -> JSONResponse:
    status_code = 200 if resultado.repetida else 201
    body = asdict(resultado)
    body.pop("repetida")
    return JSONResponse(status_code=status_code, content=body)


@app.post("/v1/contratos/{id_contrato}/autorizacoes")
def autorizar_transacao(
    id_contrato: str,
    body: AutorizacaoRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> JSONResponse:
    comando = AutorizarTransacaoComando(
        idempotency_key=idempotency_key,
        id_contrato=id_contrato,
        id_conta=body.id_conta,
        valor=body.valor,
        moeda=body.moeda,
        tipo_operacao=body.tipo_operacao,
        id_estabelecimento=body.id_estabelecimento,
    )
    resultado = _autorizar.executar(comando)
    return _responder(resultado)


@app.post("/v1/contratos/{id_contrato}/autorizacoes/{id_autorizacao}/estornos")
def estornar_autorizacao(
    id_contrato: str,
    id_autorizacao: str,
    body: EstornoRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> JSONResponse:
    comando = EstornarAutorizacaoComando(
        idempotency_key=idempotency_key,
        id_contrato=id_contrato,
        id_autorizacao_original=id_autorizacao,
        valor=body.valor,
        moeda=body.moeda,
    )
    resultado = _estornar.executar(comando)
    return _responder(resultado)


class CadastrarLimiteRequest(BaseModel):
    limite_total: str


@app.post("/internal/contratos/{id_contrato}/limites", status_code=201)
def cadastrar_limite(id_contrato: str, body: CadastrarLimiteRequest) -> dict:
    """Endpoint de bootstrap/seed para demo local — registra o limite do
    contrato diretamente no `InProcessLimiteGateway`. Não faz parte do
    contrato público; em produção o cadastro de limite é um processo de
    onboarding/backoffice no Serviço de Limites."""
    _gateway.registrar_contrato(id_contrato, body.limite_total)
    return {"id_contrato": id_contrato, "limite_total": body.limite_total}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def obter_outbox_repository():
    """Exposto para o `outbox-relay` local (`make demo`), que lê desta
    mesma instância em processo em vez de uma tabela DynamoDB real. O
    tipo concreto depende do ambiente (ver `_construir_repositorios`)."""
    return _outbox
