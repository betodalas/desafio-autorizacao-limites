"""Adapter de entrada HTTP (FastAPI) do Serviço de Limites.

Esta API é **interna** — não faz parte do `contracts/openapi.yaml` público,
que descreve apenas o Serviço de Autorização. Em produção ela seria exposta
via um API Gateway privado (VPC Link) e chamada pelo
`DynamoDbHttpLimiteGateway` do serviço de Autorização; localmente, o
adapter `InProcessLimiteGateway` chama o domínio diretamente, sem HTTP,
então este app serve principalmente para rodar o serviço de Limites de
forma isolada (ex: Postman, smoke tests, diagramas de implantação).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..application import (
    AplicarOperacaoComando,
    AplicarOperacaoLimiteUseCase,
    ConsultarSaldoLimiteUseCase,
)
from ..domain import (
    ContratoNaoEncontradoError,
    Limite,
    LimiteInsuficienteError,
    Money,
    OperacaoInvalidaError,
    TipoOperacaoDesconhecidoError,
    ValorInvalidoError,
)
from ..domain.value_objects import TipoOperacao
from .memory_repository import InMemoryLimiteRepository

app = FastAPI(
    title="Serviço de Limites (API interna)",
    version="1.0",
    description=(
        "API interna de leitura/escrita do agregado Limite. Não faz parte "
        "do contrato público — ver contracts/openapi.yaml."
    ),
)

_repository = InMemoryLimiteRepository()
_aplicar_operacao = AplicarOperacaoLimiteUseCase(_repository)
_consultar_saldo = ConsultarSaldoLimiteUseCase(_repository)


class CadastrarLimiteRequest(BaseModel):
    limite_total: str


class OperacaoRequest(BaseModel):
    id_autorizacao: str
    valor: str
    tipo_operacao: str


_PROBLEM_TYPE = "https://api.itau.com.br/problems"


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


@app.exception_handler(ContratoNaoEncontradoError)
async def _handle_contrato_nao_encontrado(request: Request, exc: ContratoNaoEncontradoError):
    return _problem(404, "Contrato não encontrado", str(exc), request.headers.get("X-Correlation-Id"))


@app.exception_handler(LimiteInsuficienteError)
async def _handle_limite_insuficiente(request: Request, exc: LimiteInsuficienteError):
    return _problem(402, "Limite insuficiente", str(exc), request.headers.get("X-Correlation-Id"))


@app.exception_handler(OperacaoInvalidaError)
async def _handle_operacao_invalida(request: Request, exc: OperacaoInvalidaError):
    return _problem(422, "Operação inválida", str(exc), request.headers.get("X-Correlation-Id"))


@app.exception_handler(TipoOperacaoDesconhecidoError)
async def _handle_tipo_desconhecido(request: Request, exc: TipoOperacaoDesconhecidoError):
    return _problem(422, "Tipo de operação desconhecido", str(exc), request.headers.get("X-Correlation-Id"))


@app.exception_handler(ValorInvalidoError)
async def _handle_valor_invalido(request: Request, exc: ValorInvalidoError):
    return _problem(422, "Valor inválido", str(exc), request.headers.get("X-Correlation-Id"))


@app.post("/internal/contratos/{id_contrato}", status_code=201)
def cadastrar_limite(id_contrato: str, body: CadastrarLimiteRequest) -> dict:
    """Endpoint de bootstrap/seed — em produção o cadastro de limite viria
    de um processo de onboarding/backoffice, fora do escopo deste desafio."""
    limite = Limite(id_contrato=id_contrato, limite_total=Money.from_str(body.limite_total))
    _repository.salvar(limite)
    return {"id_contrato": id_contrato, "limite_total": str(limite.limite_total)}


@app.get("/internal/contratos/{id_contrato}/saldo")
def consultar_saldo(id_contrato: str) -> dict:
    saldo = _consultar_saldo.executar(id_contrato)
    return {
        "id_contrato": saldo.id_contrato,
        "limite_total": str(saldo.limite_total),
        "saldo_reservado": str(saldo.saldo_reservado),
        "saldo_disponivel": str(saldo.saldo_disponivel),
    }


@app.post("/internal/contratos/{id_contrato}/operacoes", status_code=201)
def aplicar_operacao(id_contrato: str, body: OperacaoRequest) -> dict:
    comando = AplicarOperacaoComando(
        id_contrato=id_contrato,
        id_autorizacao=body.id_autorizacao,
        valor=body.valor,
        tipo_operacao=body.tipo_operacao,
    )
    evento = _aplicar_operacao.executar(comando)
    return {
        "id_contrato": evento.id_contrato,
        "id_autorizacao": evento.id_autorizacao,
        "tipo_operacao": evento.tipo_operacao.value,
        "valor": str(evento.valor),
        "saldo_reservado": str(evento.saldo_reservado),
        "ocorrido_em": evento.ocorrido_em.isoformat(),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
