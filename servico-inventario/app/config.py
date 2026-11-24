"""Configurações do serviço de Inventário, lidas das variáveis de ambiente."""
import os

# No Docker, o PostgreSQL próprio deste serviço; fora dele (testes, máquina local), um SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./inventario.db")

# Tamanho máximo do corpo de uma requisição (em bytes)
TAMANHO_MAXIMO_REQUISICAO = 64 * 1024

DOCS_ATIVA = os.getenv("DOCS", "1") == "1"
