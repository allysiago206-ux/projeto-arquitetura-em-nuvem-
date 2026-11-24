"""Configurações do serviço de Notificações, lidas das variáveis de ambiente."""
import os

# No Docker, o PostgreSQL próprio deste serviço; fora dele (testes, máquina local), um SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./notificacoes.db")

# A fila de eventos. Vazio = não consome (usado nos testes)
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/%2F")

# Tamanho máximo do corpo de uma requisição (em bytes)
TAMANHO_MAXIMO_REQUISICAO = 64 * 1024

DOCS_ATIVA = os.getenv("DOCS", "1") == "1"
