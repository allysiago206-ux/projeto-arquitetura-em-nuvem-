"""Consumidor dos eventos de Chamados, lidos da fila "notificacoes" do RabbitMQ.

- A fila é durável e as mensagens são persistentes: com este serviço parado, os eventos esperam.
- Cada mensagem só é confirmada (ack) depois de o aviso estar gravado no banco. Se o serviço cair
  antes disso, o RabbitMQ entrega a mensagem de novo quando ele voltar.
- Uma mensagem que não dá para processar (fora do formato) é recusada sem voltar para a fila
  (nack sem requeue) e vai para "notificacoes.mortas", onde pode ser examinada. Uma mensagem
  estragada não trava a fila nem some sem deixar rastro.
- Se o RabbitMQ cair, o consumidor reconecta com espera crescente: 1 s, 2 s, 4 s… até 30 s.
"""
import json
import logging
import threading

import pika
import pika.exceptions

from app import servico
from app.config import RABBITMQ_URL
from app.database import SessionLocal

log = logging.getLogger("notificacoes.consumidor")

EXCHANGE = "helpdesk"
EXCHANGE_MORTAS = "helpdesk.mortas"
FILA = "notificacoes"
FILA_MORTAS = "notificacoes.mortas"


def declarar(canal) -> None:
    """As exchanges e as filas, iguais às que o serviço de Chamados declara."""
    canal.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
    canal.exchange_declare(EXCHANGE_MORTAS, exchange_type="fanout", durable=True)
    canal.queue_declare(FILA_MORTAS, durable=True)
    canal.queue_bind(FILA_MORTAS, EXCHANGE_MORTAS)
    canal.queue_declare(FILA, durable=True, arguments={"x-dead-letter-exchange": EXCHANGE_MORTAS})
    canal.queue_bind(FILA, EXCHANGE, routing_key="chamado.*")


def processar(corpo: bytes) -> None:
    """Grava o aviso de um evento. Lança ValueError se a mensagem estiver fora do formato."""
    try:
        evento = json.loads(corpo)
        tipo, destinatario_id, mensagem = str(evento["tipo"]), int(evento["destinatario_id"]), str(evento["mensagem"])
    except (ValueError, KeyError, TypeError) as erro:
        raise ValueError(f"mensagem fora do formato ({type(erro).__name__})") from erro
    with SessionLocal() as db:
        servico.registrar(db, tipo, destinatario_id, mensagem)
    log.info("aviso %s gravado para o usuário %s", tipo, destinatario_id)


def ao_receber(canal, entrega, propriedades, corpo: bytes) -> None:
    try:
        processar(corpo)
    except ValueError as erro:
        log.error("%s: enviada para a fila %s", erro, FILA_MORTAS)
        canal.basic_nack(entrega.delivery_tag, requeue=False)
        return
    canal.basic_ack(entrega.delivery_tag)


def consumir(parar: threading.Event) -> None:
    espera = 1
    while not parar.is_set():
        try:
            conexao = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            canal = conexao.channel()
            declarar(canal)
            canal.basic_qos(prefetch_count=10)
            canal.basic_consume(FILA, ao_receber)
            log.info("lendo a fila %s", FILA)
            espera = 1
            while not parar.is_set():
                conexao.process_data_events(time_limit=1)
            conexao.close()
        except Exception as erro:  # RabbitMQ fora do ar, conexão perdida ou o banco falhando no meio
            log.warning("consumidor parado (%s); nova tentativa em %d s", type(erro).__name__, espera)
            parar.wait(espera)
            espera = min(espera * 2, 30)


_parar = threading.Event()


def iniciar() -> None:
    if not RABBITMQ_URL:
        log.warning("sem RABBITMQ_URL: nenhum evento será lido")
        return
    _parar.clear()
    threading.Thread(target=consumir, args=(_parar,), name="consumidor", daemon=True).start()


def parar() -> None:
    _parar.set()
