"""Testes de segurança do serviço de Chamados: token, permissões e entrada."""
from cryptography.hazmat.primitives.asymmetric import rsa

from tests.conftest import assinar


def test_rotas_exigem_login(cliente):
    for metodo, rota in [("get", "/chamados"), ("post", "/chamados"), ("get", "/chamados/painel"), ("get", "/chamados/1"),
                         ("patch", "/chamados/1/atribuir"), ("patch", "/chamados/1/status"), ("post", "/chamados/1/comentarios")]:
        assert getattr(cliente, metodo)(rota).status_code == 401, rota


def test_token_assinado_com_outra_chave(cliente):
    outra = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert cliente.get("/chamados", headers=assinar(1, "admin", chave=outra)).status_code == 401


def test_token_sem_assinatura_alg_none(cliente):
    assert cliente.get("/chamados", headers=assinar(1, "admin", chave=None, algoritmo="none")).status_code == 401


def test_solicitante_nao_ve_chamado_de_outra_pessoa(cliente, contas, abrir):
    cid = abrir("ana").json()["id"]
    assert cliente.get(f"/chamados/{cid}", headers=contas["bia"]).status_code == 404
    assert cliente.get("/chamados", headers=contas["bia"]).json() == []


def test_solicitante_nao_atribui_nem_resolve(cliente, contas, abrir, rede):
    cid = abrir("ana").json()["id"]
    assert cliente.patch(f"/chamados/{cid}/atribuir", headers=contas["ana"], json={"tecnico_id": 4}).status_code == 403
    assert cliente.patch(f"/chamados/{cid}/status", headers=contas["ana"], json={"status": "em_atendimento"}).status_code == 403
    assert rede.tentativas["usuarios"] == 0  # a permissão é conferida antes de qualquer consulta pela rede


def test_nao_da_para_abrir_chamado_em_nome_de_outro(abrir):
    assert abrir("ana", solicitante_id=3).status_code == 422


def test_nao_da_para_comentar_em_nome_de_outro(cliente, contas, abrir):
    cid = abrir("ana").json()["id"]
    assert cliente.post(f"/chamados/{cid}/comentarios", headers=contas["ana"], json={"texto": "oi", "autor_id": 4}).status_code == 422


def test_titulo_grande_demais(abrir):
    assert abrir(titulo="x" * 500).status_code == 422


def test_requisicao_grande_demais(cliente, contas):
    texto = '{"titulo": "' + "x" * 70000 + '"}'
    r = cliente.post("/chamados", headers={**contas["ana"], "Content-Type": "application/json"}, content=texto)
    assert r.status_code == 413


def test_texto_com_html_e_guardado_como_texto(abrir):
    r = abrir(titulo="<script>alert(1)</script>")
    assert r.status_code == 201 and r.json()["titulo"] == "<script>alert(1)</script>"


def test_cabecalhos_de_seguranca(cliente):
    r = cliente.get("/saude")
    assert r.json() == {"servico": "chamados", "banco": "ok"}
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
