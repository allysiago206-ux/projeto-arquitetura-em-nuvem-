"""Configurações do serviço de Chamados, lidas das variáveis de ambiente."""
import os

# No Docker, o PostgreSQL próprio deste serviço; fora dele (testes, máquina local), um SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chamados.db")

# Os outros serviços, pelo nome na rede do Docker
USUARIOS_URL = os.getenv("USUARIOS_URL", "http://usuarios:8000")
INVENTARIO_URL = os.getenv("INVENTARIO_URL", "http://inventario:8000")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/%2F")

# Chamadas aos outros serviços: quantas tentativas, o prazo de cada uma e a primeira espera
# entre elas (que dobra a cada nova tentativa)
TENTATIVAS = int(os.getenv("TENTATIVAS", "3"))
PRAZO_POR_TENTATIVA = float(os.getenv("PRAZO_POR_TENTATIVA", "1.0"))
ESPERA_INICIAL = float(os.getenv("ESPERA_INICIAL", "0.2"))

# Tamanho máximo do corpo de uma requisição (em bytes)
TAMANHO_MAXIMO_REQUISICAO = 64 * 1024

DOCS_ATIVA = os.getenv("DOCS", "1") == "1"
