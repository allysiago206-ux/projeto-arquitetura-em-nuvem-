"""Equipamentos de exemplo, criados quando o banco está vazio (só para aula).

Saem com os ids 1 a 3. Os chamados de exemplo usam o 1 (desktop) e o 2 (impressora).
"""
from sqlalchemy.orm import Session

from app import servico
from app.esquemas import AtivoCriar


def carregar(db: Session) -> None:
    if servico.listar(db):
        return
    for patrimonio, tipo, descricao, setor in [
        ("PAT-0001", "computador", "Desktop Dell OptiPlex", "Financeiro"),
        ("PAT-0002", "impressora", "Impressora HP LaserJet", "RH"),
        ("PAT-0003", "notebook", "Notebook Lenovo ThinkPad", "TI"),
    ]:
        servico.criar(db, AtivoCriar(patrimonio=patrimonio, tipo=tipo, descricao=descricao, setor=setor))
