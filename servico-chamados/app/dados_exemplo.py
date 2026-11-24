"""Chamados de exemplo, criados quando o banco está vazio (só para aula).

Usam os ids dos dados de exemplo dos outros serviços: Ana 2, Bruno 3 e Carla 4 (Usuários), o
desktop 1 e a impressora 2 (Inventário). São gravados direto, sem consultar a rede nem publicar
eventos: na primeira subida, os outros serviços podem ainda não estar prontos.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app import repositorio
from app.modelos import Chamado
from app.servico import PRIORIDADES, calcular_prazo, registrar

ANA, BRUNO, CARLA = 2, 3, 4


def carregar(db: Session) -> None:
    if repositorio.listar(db):
        return
    agora = datetime.now()
    for titulo, descricao, prioridade, solicitante, ativo, tecnico in [
        ("Computador não liga", "Apertei o botão e nada acontece.", "alta", ANA, 1, CARLA),
        ("Impressora atolando papel", "Atola a cada 3 folhas.", "media", BRUNO, 2, None),
        ("Acesso ao sistema de RH", "Preciso de acesso para a nova estagiária.", "baixa", BRUNO, None, None),
    ]:
        chamado = Chamado(titulo=titulo, descricao=descricao, prioridade=prioridade, solicitante_id=solicitante,
                          ativo_id=ativo, tecnico_id=tecnico, status="em_atendimento" if tecnico else "aberto",
                          criado_em=agora, prazo_sla=calcular_prazo(prioridade, agora))
        registrar(chamado, solicitante, "aberto", f"Chamado aberto com prioridade {PRIORIDADES[prioridade]}")
        if tecnico:
            registrar(chamado, tecnico, "atribuido", "Atribuído a Carla Dias e atendimento iniciado")
        repositorio.salvar(db, chamado)
