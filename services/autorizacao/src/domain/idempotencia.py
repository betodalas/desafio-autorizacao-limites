"""Registro de idempotência — associa uma `Idempotency-Key` ao hash do
payload original e, quando concluído, ao resultado a ser devolvido em
reenvios (HTTP 200)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class StatusIdempotencia(str, Enum):
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONCLUIDO = "CONCLUIDO"


def calcular_hash_payload(payload: dict[str, Any]) -> str:
    """Hash estável e determinístico do payload da requisição, usado para
    detectar reuso de uma Idempotency-Key com payload divergente."""
    chaves_ordenadas = sorted(payload.items())
    bruto = repr(chaves_ordenadas).encode("utf-8")
    return hashlib.sha256(bruto).hexdigest()


@dataclass
class RegistroIdempotencia:
    idempotency_key: str
    hash_payload: str
    status: StatusIdempotencia
    id_autorizacao: str
    resultado: Optional[dict[str, Any]] = None

    @classmethod
    def iniciar(
        cls, idempotency_key: str, hash_payload: str, id_autorizacao: str
    ) -> "RegistroIdempotencia":
        return cls(
            idempotency_key=idempotency_key,
            hash_payload=hash_payload,
            status=StatusIdempotencia.EM_ANDAMENTO,
            id_autorizacao=id_autorizacao,
        )

    def concluir(self, resultado: dict[str, Any]) -> None:
        self.status = StatusIdempotencia.CONCLUIDO
        self.resultado = resultado
