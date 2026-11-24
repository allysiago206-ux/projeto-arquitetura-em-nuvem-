from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app import seguranca

PC = {"patrimonio": "PAT-1", "tipo": "computador", "descricao": "Desktop", "setor": "TI"}


# ---------- funcionamento ----------

def test_tecnico_cadastra_ativo_e_filtra_por_setor(cliente, contas):
    cliente.post("/ativos", headers=contas["carla"], json={"patrimonio": "PAT-1", "tipo": "impressora", "descricao": "HP", "setor": "RH"})
    cliente.post("/ativos", headers=contas["carla"], json={"patrimonio": "PAT-2", "tipo": "computador", "descricao": "Dell", "setor": "TI"})
    assert len(cliente.get("/ativos", params={"setor": "RH"}, headers=contas["carla"]).json()) == 1


def test_consulta_que_chamados_faz(cliente, contas):
    ativo = cliente.post("/ativos", headers=contas["carla"], json=PC).json()
    assert cliente.get(f"/ativos/{ativo['id']}", headers=contas["ana"]).json()["patrimonio"] == "PAT-1"


def test_ativo_inexistente(cliente, contas):
    assert cliente.get("/ativos/99", headers=contas["ana"]).status_code == 404


def test_patrimonio_repetido(cliente, contas):
    cliente.post("/ativos", headers=contas["carla"], json=PC)
    assert cliente.post("/ativos", headers=contas["carla"], json=PC).status_code == 422


def test_saude_confere_o_banco(cliente):
    assert cliente.get("/saude").json() == {"servico": "inventario", "banco": "ok"}


# ---------- segurança ----------

def test_rotas_exigem_login(cliente):
    for metodo, rota in [("get", "/ativos"), ("get", "/ativos/1"), ("post", "/ativos")]:
        assert getattr(cliente, metodo)(rota).status_code == 401, rota


def test_solicitante_nao_cadastra_ativo(cliente, contas):
    assert cliente.post("/ativos", headers=contas["ana"], json=PC).status_code == 403


def test_token_assinado_com_outra_chave(cliente, token):
    outra = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert cliente.post("/ativos", headers=token(1, "admin", chave=outra), json=PC).status_code == 401


def test_token_sem_assinatura_alg_none(cliente, token):
    assert cliente.get("/ativos", headers=token(1, "admin", chave=None, algoritmo="none")).status_code == 401


def test_token_expirado(cliente, token):
    antigo = datetime.now(timezone.utc) - timedelta(hours=2)
    assert cliente.get("/ativos", headers=token(4, "tecnico", iat=antigo, exp=antigo + timedelta(minutes=5))).status_code == 401


def test_patrimonio_com_caractere_invalido(cliente, contas):
    assert cliente.post("/ativos", headers=contas["carla"], json={**PC, "patrimonio": "PAT 1; DROP"}).status_code == 422


def test_campo_extra_e_recusado(cliente, contas):
    assert cliente.post("/ativos", headers=contas["carla"], json={**PC, "id": 50}).status_code == 422


def test_requisicao_grande_demais(cliente, contas):
    texto = '{"descricao": "' + "x" * 70000 + '"}'
    r = cliente.post("/ativos", headers={**contas["carla"], "Content-Type": "application/json"}, content=texto)
    assert r.status_code == 413


def test_cabecalhos_de_seguranca(cliente):
    r = cliente.get("/saude")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"


# ---------- a chave pública vinda de Usuários ----------

@pytest.fixture
def usuarios_fora(monkeypatch):
    def recusar(*a, **k):
        raise httpx.ConnectError("conexão recusada")
    monkeypatch.setattr(seguranca.httpx, "get", recusar)
    monkeypatch.setattr(seguranca.time, "sleep", lambda s: None)  # as esperas entre tentativas não atrasam o teste


def test_sem_chave_e_com_usuarios_fora_responde_503(usuarios_fora, monkeypatch):
    monkeypatch.setitem(seguranca._chave, "pem", None)
    with pytest.raises(HTTPException) as erro:
        seguranca.chave_publica()
    assert erro.value.status_code == 503


def test_com_usuarios_fora_segue_a_ultima_chave(usuarios_fora, monkeypatch):
    monkeypatch.setitem(seguranca._chave, "pem", "chave-guardada")
    monkeypatch.setitem(seguranca._chave, "buscada_em", -10_000.0)  # vencida: tenta buscar, falha, usa a guardada
    assert seguranca.chave_publica() == "chave-guardada"
