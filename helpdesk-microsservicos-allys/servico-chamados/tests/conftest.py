"""Testes do serviço de Chamados com a rede simulada.

Usuários e Inventário são simulados: respondem como os serviços de verdade, contam as tentativas
e podem estar fora do ar, lentos ou falhar só por um instante. Os eventos vão para uma lista, em
vez do RabbitMQ, e os tokens são assinados com uma chave de teste.
"""
import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["DADOS_EXEMPLO"] = "0"
os.environ["USUARIOS_URL"] = "http://usuarios"
os.environ["INVENTARIO_URL"] = "http://inventario"

import time  # noqa: E402
from collections import Counter  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from urllib.parse import urlparse  # noqa: E402

import httpx  # noqa: E402
import jwt  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import clientes, eventos, seguranca  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

CHAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLICA = CHAVE.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
USUARIOS = {1: ("Admin", "admin"), 2: ("Ana", "solicitante"), 3: ("Bia", "solicitante"), 4: ("Carla Dias", "tecnico")}
ATIVOS = {1: {"id": 1, "patrimonio": "PAT-1", "tipo": "computador", "descricao": "Desktop", "setor": "TI"}}


class RedeSimulada:
    def __init__(self):
        self.fora_do_ar: set[str] = set()
        self.lentos: set[str] = set()
        self.falhas_passageiras: Counter = Counter()  # quantas vezes o serviço falha antes de responder
        self.tentativas: Counter = Counter()
        self.cabecalhos: list[dict] = []

    def get(self, url, headers=None, timeout=None):
        endereco = urlparse(url)
        servico = endereco.hostname
        self.tentativas[servico] += 1
        self.cabecalhos.append(dict(headers or {}))
        if servico in self.fora_do_ar:
            raise httpx.ConnectError("conexão recusada")
        if self.falhas_passageiras[servico]:
            self.falhas_passageiras[servico] -= 1
            raise httpx.ConnectError("conexão recusada (por um instante)")
        if servico in self.lentos:
            time.sleep(timeout + 0.3)
        ident = int(endereco.path.rstrip("/").rsplit("/", 1)[1])
        if servico == "usuarios" and ident in USUARIOS:
            nome, perfil = USUARIOS[ident]
            return httpx.Response(200, json={"id": ident, "nome": nome, "perfil": perfil})
        if servico == "inventario" and ident in ATIVOS:
            return httpx.Response(200, json=ATIVOS[ident])
        return httpx.Response(404, json={"detail": "não encontrado"})


@pytest.fixture
def rede(monkeypatch):
    simulada = RedeSimulada()
    monkeypatch.setattr(clientes.httpx, "get", simulada.get)
    monkeypatch.setattr(clientes, "PRAZO_POR_TENTATIVA", 0.2)  # os testes não esperam o prazo de verdade
    monkeypatch.setattr(clientes, "ESPERA_INICIAL", 0.01)
    return simulada


@pytest.fixture
def enviados(monkeypatch):
    lista = []
    monkeypatch.setattr(eventos, "enviar", lambda tipo, destinatario_id, mensagem, chamado_id: lista.append((tipo, destinatario_id)))
    return lista


@pytest.fixture
def cliente(monkeypatch, rede, enviados):
    monkeypatch.setattr(seguranca, "chave_publica", lambda: PUBLICA)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def db_de_teste():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = db_de_teste
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def assinar(usuario_id, perfil, chave=CHAVE, algoritmo="RS256"):
    agora = datetime.now(timezone.utc)
    dados = {"sub": str(usuario_id), "perfil": perfil, "iss": "helpdesk-ti", "iat": agora, "exp": agora + timedelta(hours=1)}
    return {"Authorization": f"Bearer {jwt.encode(dados, chave, algorithm=algoritmo)}"}


@pytest.fixture
def contas():
    return {"admin": assinar(1, "admin"), "ana": assinar(2, "solicitante"), "bia": assinar(3, "solicitante"),
            "carla": assinar(4, "tecnico")}


@pytest.fixture
def abrir(cliente, contas):
    def abrir(quem="ana", prioridade="alta", **extra):
        dados = {"titulo": "PC não liga", "descricao": "Nada acontece", "prioridade": prioridade, "ativo_id": 1, **extra}
        return cliente.post("/chamados", headers=contas[quem], json=dados)
    return abrir
