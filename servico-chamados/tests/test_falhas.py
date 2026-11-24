"""Quando Usuários, Inventário ou o RabbitMQ falham: novas tentativas, prazo e erro claro."""
import time

import pika
import pika.exceptions

from app import clientes, eventos


def test_falha_passageira_se_resolve_na_segunda_tentativa(abrir, rede):
    rede.falhas_passageiras["inventario"] = 1
    assert abrir().status_code == 201  # o usuário nem percebe
    assert rede.tentativas["inventario"] == 2


def test_inventario_fora_do_ar_tenta_3_vezes_e_responde_503(abrir, rede):
    rede.fora_do_ar.add("inventario")
    r = abrir()
    assert r.status_code == 503 and r.headers["retry-after"] == "5"
    assert r.json()["detail"] == ("Inventário indisponível no momento (3 tentativas sem resposta). "
                                  "Tente novamente em alguns segundos.")
    assert rede.tentativas["inventario"] == clientes.TENTATIVAS


def test_inventario_fora_do_ar_nao_impede_o_resto(cliente, contas, abrir, rede):
    rede.fora_do_ar.add("inventario")
    assert abrir(ativo_id=None).status_code == 201
    assert cliente.get("/chamados", headers=contas["carla"]).status_code == 200
    assert cliente.get("/chamados/painel", headers=contas["carla"]).status_code == 200


def test_servico_lento_estoura_o_prazo_de_cada_tentativa(abrir, rede):
    rede.lentos.add("inventario")
    inicio = time.monotonic()
    assert abrir().status_code == 503
    assert time.monotonic() - inicio < 2  # 3 tentativas de 0,2 s mais as esperas, não o tempo do serviço lento


def test_resposta_definitiva_nao_e_repetida(abrir, rede):
    abrir(ativo_id=999)  # 404: tentar de novo não muda nada
    assert rede.tentativas["inventario"] == 1


def test_usuarios_fora_do_ar_na_atribuicao(cliente, contas, abrir, rede):
    cid = abrir().json()["id"]
    rede.fora_do_ar.add("usuarios")
    r = cliente.patch(f"/chamados/{cid}/atribuir", headers=contas["carla"], json={"tecnico_id": 4})
    assert r.status_code == 503 and r.json()["detail"].startswith("Usuários indisponível")


def test_repassa_o_token_do_usuario(cliente, contas, abrir, rede):
    abrir("ana")
    assert rede.cabecalhos[-1]["Authorization"] == contas["ana"]["Authorization"]


# ---------- RabbitMQ ----------

class CanalAnotado:
    def __init__(self):
        self.chamadas = []

    def __getattr__(self, nome):
        return lambda *a, **k: self.chamadas.append((nome, a, k))


def test_fila_duravel_com_fila_de_mensagens_mortas():
    canal = CanalAnotado()
    eventos.declarar(canal)
    filas = {a[0]: k for nome, a, k in canal.chamadas if nome == "queue_declare"}
    assert filas["notificacoes"] == {"durable": True, "arguments": {"x-dead-letter-exchange": "helpdesk.mortas"}}
    assert filas["notificacoes.mortas"] == {"durable": True}


def test_rabbitmq_fora_do_ar_nao_derruba_o_servico(monkeypatch):
    def recusar(*a, **k):
        raise pika.exceptions.AMQPConnectionError("RabbitMQ fora do ar")
    monkeypatch.setattr(eventos.pika, "BlockingConnection", recusar)
    monkeypatch.setattr(eventos.time, "sleep", lambda s: None)
    assert eventos.publicar("ChamadoAberto", 2, "aviso", 1) is False  # tentou, registrou no log e seguiu
