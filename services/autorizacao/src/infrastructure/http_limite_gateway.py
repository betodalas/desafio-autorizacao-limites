"""Adapter de `LimiteGateway` via HTTP — usado quando Autorização e
Limites rodam como serviços/containers separados (k8s local ou
produção), chamando a API interna do Serviço de Limites
(`services/limites/src/infrastructure/api.py`).

Em produção, a URL apontaria para o endpoint privado do Serviço de
Limites atrás do API Gateway/VPC Link; localmente (kind), aponta para o
Service do Kubernetes (ex.: `http://limites:8080`).
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from ..domain import LimiteGatewayIndeterminadoError, LimiteInsuficienteError, LimiteOperacaoInvalidaError
from ..domain.ports import LimiteGateway, LimiteGatewayResultado
from ..domain.value_objects import Money, TipoOperacao


class HttpLimiteGateway(LimiteGateway):
    def __init__(self, base_url: Optional[str] = None, timeout_segundos: float = 5.0):
        self._base_url = (base_url or os.environ.get("LIMITES_SERVICE_URL", "http://limites:8080")).rstrip("/")
        self._timeout = timeout_segundos

    def aplicar_operacao(
        self,
        id_contrato: str,
        id_autorizacao: str,
        valor: Money,
        tipo_operacao: TipoOperacao,
    ) -> LimiteGatewayResultado:
        url = f"{self._base_url}/internal/contratos/{id_contrato}/operacoes"
        corpo = {
            "id_autorizacao": id_autorizacao,
            "valor": str(valor),
            "tipo_operacao": tipo_operacao.value,
        }
        try:
            resposta = httpx.post(url, json=corpo, timeout=self._timeout)
        except httpx.TransportError as exc:
            raise LimiteGatewayIndeterminadoError(f"Falha de rede ao chamar Limites: {exc}") from exc

        if resposta.status_code == 201:
            dados = resposta.json()
            return LimiteGatewayResultado(saldo_reservado=Money.from_str(dados["saldo_reservado"]))
        if resposta.status_code == 402:
            raise LimiteInsuficienteError(resposta.json().get("detail", "Limite insuficiente"))
        if resposta.status_code == 422:
            raise LimiteOperacaoInvalidaError(resposta.json().get("detail", "Operação de limite inválida"))
        # 5xx / timeouts / respostas inesperadas: estado indeterminado,
        # tratado pela saga como PENDENTE + sweeper (ADR 04).
        raise LimiteGatewayIndeterminadoError(
            f"Resposta indeterminada do Serviço de Limites: HTTP {resposta.status_code}"
        )

    def registrar_contrato(self, id_contrato: str, limite_total: str) -> None:
        """Proxy de conveniência para o endpoint de seed do Serviço de
        Limites — usado pelo `make demo` em modo containers/k8s, onde o
        endpoint `/internal/contratos/{id}/limites` de Autorização apenas
        repassa a chamada (ver api.py)."""
        url = f"{self._base_url}/internal/contratos/{id_contrato}"
        httpx.post(url, json={"limite_total": limite_total}, timeout=self._timeout)

    def consultar_reserva(
        self, id_contrato: str, id_autorizacao: str
    ) -> Optional[LimiteGatewayResultado]:
        url = f"{self._base_url}/internal/contratos/{id_contrato}/saldo"
        try:
            resposta = httpx.get(url, timeout=self._timeout)
        except httpx.TransportError:
            return None
        if resposta.status_code != 200:
            return None
        # A API de saldo não expõe reservas individuais por id_autorizacao
        # (ver services/limites/src/infrastructure/api.py); o sweeper usa
        # este retorno apenas como sinal best-effort de que o contrato
        # está acessível — reconciliação fina ficaria a cargo de um
        # endpoint dedicado de consulta de reserva, fora do escopo atual.
        return None
