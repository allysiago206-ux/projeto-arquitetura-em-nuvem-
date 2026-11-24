"""Usuários de exemplo, criados quando o banco está vazio (só para aula).

Saem com os ids 1 a 5, nesta ordem. Os chamados de exemplo, no serviço de Chamados, usam os mesmos.
Em produção, rode com DADOS_EXEMPLO=0.
"""
import os

from sqlalchemy.orm import Session

from app import servico
from app.esquemas import UsuarioCriar


def carregar(db: Session) -> None:
    if servico.listar(db):
        return
    senha = os.getenv("SENHA_EXEMPLO", "Helpdesk2026")
    for nome, email, perfil in [
        ("Admin TI", "admin@empresa.com", "admin"),
        ("Ana Souza", "ana@empresa.com", "solicitante"),
        ("Bruno Lima", "bruno@empresa.com", "solicitante"),
        ("Carla Dias", "carla@empresa.com", "tecnico"),
        ("Diego Rocha", "diego@empresa.com", "tecnico"),
    ]:
        servico.criar(db, UsuarioCriar(nome=nome, email=email, perfil=perfil, senha=senha))
