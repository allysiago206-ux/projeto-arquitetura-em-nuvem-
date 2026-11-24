"""Testes de segurança do serviço de Usuários: login, token RS256, senhas, permissões e entrada."""
import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app import chaves, config, limite
from app.modelos import Usuario


def corpo(sub, **extra):
    agora = datetime.now(timezone.utc)
    return {"sub": str(sub), "perfil": "admin", "iss": config.JWT_EMISSOR, "iat": agora,
            "exp": agora + timedelta(hours=1), **extra}


def com(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- autenticação ----------

def test_rotas_exigem_login(cliente, contas):
    for metodo, rota in [("get", "/usuarios"), ("get", "/usuarios/1"), ("post", "/usuarios"), ("get", "/auth/eu")]:
        assert getattr(cliente, metodo)(rota).status_code == 401, rota


def test_login_com_senha_errada(cliente, contas):
    r = cliente.post("/auth/login", json={"email": "ana@x.com", "senha": "errada123"})
    assert r.status_code == 401 and r.json()["detail"] == "E-mail ou senha inválidos."


def test_login_com_email_inexistente_tem_a_mesma_mensagem(cliente, contas):
    r = cliente.post("/auth/login", json={"email": "ninguem@x.com", "senha": "errada123"})
    assert r.status_code == 401 and r.json()["detail"] == "E-mail ou senha inválidos."


def test_bloqueio_apos_varias_senhas_erradas(cliente, contas, senha):
    for _ in range(config.LOGIN_MAX_FALHAS):
        cliente.post("/auth/login", json={"email": "ana@x.com", "senha": "errada123"})
    assert cliente.post("/auth/login", json={"email": "ana@x.com", "senha": senha}).status_code == 429


def test_token_adulterado(cliente, contas):
    token = contas["ana"]["headers"]["Authorization"] + "x"
    assert cliente.get("/auth/eu", headers={"Authorization": token}).status_code == 401


def test_token_assinado_com_outra_chave(cliente, contas):
    outra = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    falso = jwt.encode(corpo(contas["admin"]["id"]), outra, algorithm="RS256")
    assert cliente.get("/auth/eu", headers=com(falso)).status_code == 401


def test_confusao_de_algoritmo_e_recusada(cliente, contas):
    """O ataque clássico do RS256: assinar em HS256 usando a chave pública (que é pública) como segredo.
    O PyJWT nem aceita assinar assim, então o token falso é montado à mão."""
    def b64(dados: bytes) -> bytes:
        return base64.urlsafe_b64encode(dados).rstrip(b"=")
    dados = {k: int(v.timestamp()) if isinstance(v, datetime) else v for k, v in corpo(contas["admin"]["id"]).items()}
    cabecalho, conteudo = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()), b64(json.dumps(dados).encode())
    assinatura = b64(hmac.new(chaves.publica().encode(), cabecalho + b"." + conteudo, hashlib.sha256).digest())
    falso = b".".join([cabecalho, conteudo, assinatura]).decode()
    assert cliente.get("/auth/eu", headers=com(falso)).status_code == 401


def test_token_sem_assinatura_alg_none(cliente, contas):
    falso = jwt.encode(corpo(contas["admin"]["id"]), None, algorithm="none")
    assert cliente.get("/auth/eu", headers=com(falso)).status_code == 401


def test_token_expirado(cliente, contas):
    antigo = datetime.now(timezone.utc) - timedelta(hours=2)
    vencido = jwt.encode(corpo(contas["ana"]["id"], iat=antigo, exp=antigo + timedelta(minutes=5)),
                         chaves.privada(), algorithm="RS256")
    assert cliente.get("/auth/eu", headers=com(vencido)).status_code == 401


def test_usuario_desativado_perde_o_acesso(sessao, cliente, contas):
    with sessao() as db:
        db.get(Usuario, contas["ana"]["id"]).ativo = False
        db.commit()
    assert cliente.get("/auth/eu", headers=contas["ana"]["headers"]).status_code == 401


def test_senha_guardada_com_hash(sessao, contas, senha):
    with sessao() as db:
        u = db.query(Usuario).filter_by(email="ana@x.com").one()
        assert senha not in u.senha_hash and u.senha_hash.startswith("scrypt$")


def test_senha_fraca_e_recusada(cliente, contas):
    r = cliente.post("/usuarios", headers=contas["admin"]["headers"],
                     json={"nome": "Eva", "email": "eva@x.com", "perfil": "solicitante", "senha": "abcdefgh"})
    assert r.status_code == 422


# ---------- a chave ----------

def test_chave_publica_nao_revela_a_privada(cliente):
    r = cliente.get("/auth/chave-publica").json()
    assert r["algoritmo"] == "RS256"
    assert "BEGIN PUBLIC KEY" in r["chave_publica"] and "PRIVATE" not in r["chave_publica"]


def test_sem_chave_no_env_gera_e_guarda_no_banco(sessao, monkeypatch):
    monkeypatch.setattr(chaves, "JWT_CHAVE_PRIVADA", "")
    with sessao() as db:
        chaves.preparar(db)
        primeira = chaves.publica()
        chaves.preparar(db)  # um reinício do serviço: lê a mesma chave do banco, não gera outra
        assert chaves.publica() == primeira
        assert db.query(chaves.ChaveAssinatura).count() == 1


# ---------- permissões e entrada ----------

def test_solicitante_nao_cria_usuario(cliente, contas):
    r = cliente.post("/usuarios", headers=contas["ana"]["headers"],
                     json={"nome": "Eva", "email": "eva@x.com", "perfil": "admin", "senha": "Forte1234"})
    assert r.status_code == 403


def test_requisicao_grande_demais(cliente, contas):
    texto = '{"nome": "' + "x" * 70000 + '"}'
    r = cliente.post("/usuarios", headers={**contas["admin"]["headers"], "Content-Type": "application/json"}, content=texto)
    assert r.status_code == 413


def test_cabecalhos_de_seguranca(cliente):
    r = cliente.get("/saude")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
