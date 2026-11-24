"""Testes do serviço de Inventário: banco em memória e um par de chaves de teste.

Os tokens são assinados aqui mesmo, com a chave privada de teste; o serviço os confere com a
chave pública correspondente, como faria com a do serviço de Usuários.
"""
import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["DADOS_EXEMPLO"] = "0"

from datetime import datetime, timedelta, timezone  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import seguranca  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

CHAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLICA = CHAVE.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def assinar(usuario_id, perfil, chave=CHAVE, algoritmo="RS256", **extra):
    agora = datetime.now(timezone.utc)
    dados = {"sub": str(usuario_id), "perfil": perfil, "iss": "helpdesk-ti", "iat": agora,
             "exp": agora + timedelta(hours=1), **extra}
    return {"Authorization": f"Bearer {jwt.encode(dados, chave, algorithm=algoritmo)}"}


@pytest.fixture
def token():
    return assinar


@pytest.fixture
def cliente(monkeypatch):
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


@pytest.fixture
def contas():
    return {"admin": assinar(1, "admin"), "ana": assinar(2, "solicitante"), "carla": assinar(4, "tecnico")}
