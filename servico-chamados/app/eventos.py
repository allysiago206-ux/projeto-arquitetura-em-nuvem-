"""Eventos de Chamados, publicados no RabbitMQ.

Chamados não chama mais o módulo de notificações: publica o fato (ChamadoAberto, ChamadoAtribuido,
ChamadoResolvido) na exchange "helpdesk" e segue. A fila "notificacoes" é durável e cada mensagem
é persistente: com o serviço de Notificações parado, elas esperam na fila, mesmo que o RabbitMQ
reinicie. Uma mensagem que o consumidor não consegue processar vai para "notificacoes.mortas", em
vez de se perder ou travar a fila.

As filas são declaradas aqui também (declarar de novo não muda nada): assim, um evento publicado
antes de Notificações subir pela primeira vez já encontra a fila esperando.
"""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pika
import pika.exceptions

from app.config import RABBITMQ_URL

log = logging.getLogger("chamados.eventos")

EXCHANGE = "helpdesk"
EXCHANGE_MORTAS = "helpdesk.mortas"
FILA = "notificacoes"
FILA_MORTAS = "notificacoes.mortas"
ROTAS = {"ChamadoAberto": "chamado.aberto", "ChamadoAtribuido": "chamado.atribuido", "ChamadoResolvido": "chamado.resolvido"}


def declarar(canal) -> None:
    """As exchanges e as filas, iguais no publicador e no consumidor."""
    canal.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
    canal.exchange_declare(EXCHANGE_MORTAS, exchange_type="fanout", durable=True)
    canal.queue_declare(FILA_MORTAS, durable=True)
    canal.queue_bind(FILA_MORTAS, EXCHANGE_MORTAS)
    canal.queue_declare(FILA, durable=True, arguments={"x-dead-letter-exchange": EXCHANGE_MORTAS})
    canal.queue_bind(FILA, EXCHANGE, routing_key="chamado.*")


def publicar(tipo: str, destinatario_id: int, mensagem: str, chamado_id: int) -> bool:
    """Publica o evento, com até três tentativas. Se o RabbitMQ estiver fora, o chamado segue
    valendo e o aviso fica registrado no log como não enviado."""
    corpo = json.dumps({"tipo": tipo, "destinatario_id": destinatario_id, "mensagem": mensagem,
                        "chamado_id": chamado_id, "quando": datetime.now(timezone.utc).isoformat()}).encode()
    parametros = pika.URLParameters(RABBITMQ_URL)
    parametros.socket_timeout = 2
    parametros.blocked_connection_timeout = 2
    parametros.connection_attempts = 1
    for tentativa, espera in enumerate((0.3, 0.6, None), start=1):
        try:
            conexao = pika.BlockingConnection(parametros)
            try:
                canal = conexao.channel()
                declarar(canal)
                canal.confirm_delivery()  # o RabbitMQ confirma que guardou a mensagem
                canal.basic_publish(EXCHANGE, ROTAS[tipo], corpo, pika.BasicProperties(
                    content_type="application/json", delivery_mode=pika.DeliveryMode.Persistent))
            finally:
                conexao.close()
            log.info("evento %s do chamado #%s publicado", tipo, chamado_id)
            return True
        except pika.exceptions.AMQPError as erro:
            log.warning("RabbitMQ: tentativa %d de 3 falhou (%s)", tentativa, type(erro).__name__)
            if espera:
                time.sleep(espera)
    # ponytail: sem tabela de saída (outbox); com o RabbitMQ fora, o aviso se perde. Criar a tabela se isso importar
    log.error("evento %s do chamado #%s não publicado: RabbitMQ fora do ar", tipo, chamado_id)
    return False


# Uma thread só: os eventos saem na ordem em que aconteceram, e quem abriu o chamado não espera o RabbitMQ
_envios = ThreadPoolExecutor(max_workers=1, thread_name_prefix="eventos")


def enviar(tipo: str, destinatario_id: int, mensagem: str, chamado_id: int) -> None:
    """Agenda a publicação em segundo plano e volta na hora."""
    _envios.submit(publicar, tipo, destinatario_id, mensagem, chamado_id)
