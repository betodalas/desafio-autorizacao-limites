"""Test doubles para o worker de relay — não dependem de nenhum serviço
concreto, apenas da estrutura mínima exigida pelos ports."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.ports import EventPublisher, OutboxSource


@dataclass
class RegistroFake:
    event_id: str
    tentativas: int = 0
    status: str = "PENDENTE"
    ultimo_erro: str | None = None
    payload: dict = field(default_factory=dict)

    def para_envelope(self) -> dict:
        return {**self.payload, "event_id": self.event_id}


class FakeOutboxSource(OutboxSource):
    def __init__(self, registros: list[RegistroFake] | None = None):
        self._registros = {r.event_id: r for r in (registros or [])}
        self.max_tentativas = 3

    def adicionar(self, registro: RegistroFake) -> None:
        self._registros[registro.event_id] = registro

    def listar_pendentes(self, limite: int = 50) -> list[RegistroFake]:
        pendentes = [r for r in self._registros.values() if r.status == "PENDENTE"]
        return pendentes[:limite]

    def marcar_publicado(self, event_id: str) -> None:
        self._registros[event_id].status = "PUBLICADO"

    def marcar_falha(self, event_id: str, erro: str) -> None:
        registro = self._registros[event_id]
        registro.tentativas += 1
        registro.ultimo_erro = erro
        if registro.tentativas >= self.max_tentativas:
            registro.status = "FALHA"


class FakePublisher(EventPublisher):
    def __init__(self) -> None:
        self.publicados: list[dict] = []
        self.falhar_para: set[str] = set()

    def publicar(self, envelope: dict) -> None:
        if envelope.get("event_id") in self.falhar_para:
            raise RuntimeError("falha simulada de publicação")
        self.publicados.append(envelope)
