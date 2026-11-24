"""Configurações do serviço de Usuários, lidas das variáveis de ambiente."""
import os

# No Docker, o PostgreSQL próprio deste serviço; fora dele (testes, máquina local), um SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./usuarios.db")

# Chave privada RSA (formato PEM) que assina os tokens. Opcional: sem ela, o serviço gera uma
# na primeira subida e a guarda no próprio banco. No .env, numa linha só, com \n no lugar das quebras.
JWT_CHAVE_PRIVADA = os.getenv("JWT_CHAVE_PRIVADA", "").replace("\\n", "\n")
JWT_ALGORITMO = "RS256"
JWT_EMISSOR = "helpdesk-ti"
TOKEN_MINUTOS = int(os.getenv("TOKEN_MINUTOS", "60"))

# Proteção contra tentativas de adivinhar senhas
LOGIN_MAX_FALHAS = int(os.getenv("LOGIN_MAX_FALHAS", "5"))
LOGIN_JANELA_SEGUNDOS = int(os.getenv("LOGIN_JANELA_SEGUNDOS", "300"))

# Tamanho máximo do corpo de uma requisição (em bytes)
TAMANHO_MAXIMO_REQUISICAO = 64 * 1024

DOCS_ATIVA = os.getenv("DOCS", "1") == "1"
