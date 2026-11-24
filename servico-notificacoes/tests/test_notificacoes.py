import json
from types import SimpleNamespace

import pika.exceptions
from cryptography.hazmat.primitives.asymmetric import rsa

from app import consumidor
from tests.conftest import assinar


def evento(tipo, destinatario_id, mensagem="aviso"):
    """Uma mensagem como o serviço de Chamados publica no RabbitMQ."""
    return json.dumps({"tipo": tipo, "destinatario_id": destinatario_id, "mensagem": mensagem, "chamado_id": 1}).encode()


class CanalFalso:
    def __init__(self):
        self.confirmadas, self.recusadas = [], []

    def basic_ack(self, tag):
        self.confirmadas.append(tag)

    def basic_nack(self, tag, requeue):
        self.recusadas.append((tag, requeue))


def receber(canal, tag, corpo):
    consumidor.ao_receber(canal, SimpleNamespace(delivery_tag=tag), None, corpo)


def test_evento_vira_aviso_so_do_destinatario(cliente, contas):
    receber(CanalFalso(), 1, evento("ChamadoAberto", 2, "Seu chamado #1 foi aberto."))
    avisos = cliente.get("/notificacoes", headers=contas["ana"]).json()
    assert [(a["tipo"], a["mensagem"]) for a in avisos] == [("ChamadoAberto", "Seu chamado #1 foi aberto.")]
    assert cliente.get("/notificacoes", headers=contas["bia"]).json() == []


def test_confirma_depois_de_gravar(cliente):
    canal = CanalFalso()
    receber(canal, 7, evento("ChamadoAtribuido", 4))
    assert canal.confirmadas == [7] and canal.recusadas == []


def test_mensagem_estragada_vai_para_a_fila_de_mortas(cliente, contas):
    canal = CanalFalso()
    receber(canal, 8, b"isto nao e json")
    receber(canal, 9, json.dumps({"tipo": "ChamadoAberto"}).encode())  # falta o destinatário
    assert canal.recusadas == [(8, False), (9, False)]  # sem voltar para a fila: vai para a de mortas
    assert canal.confirmadas == []


def test_consumidor_tenta_de_novo_com_espera_crescente(monkeypatch):
    esperas = []

    class Parada:
        def is_set(self):
            return len(esperas) >= 4

        def wait(self, segundos):
            esperas.append(segundos)

    def recusar(*a, **k):
        raise pika.exceptions.AMQPConnectionError("RabbitMQ fora do ar")
    monkeypatch.setattr(consumidor.pika, "BlockingConnection", recusar)
    consumidor.consumir(Parada())
    assert esperas == [1, 2, 4, 8]


# ---------- segurança ----------

def test_rota_exige_login(cliente):
    assert cliente.get("/notificacoes").status_code == 401


def test_token_assinado_com_outra_chave(cliente):
    outra = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert cliente.get("/notificacoes", headers=assinar(2, "solicitante", chave=outra)).status_code == 401


def test_cabecalhos_de_seguranca(cliente):
    r = cliente.get("/saude")
    assert r.json() == {"servico": "notificacoes", "banco": "ok"}
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
