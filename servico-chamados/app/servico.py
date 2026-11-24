"""Regras do serviço de Chamados.

As regras são as do monólito (SLA, transições de status, permissões). Mudaram as dependências:
o técnico e o equipamento são conferidos pela rede (`clientes`), os avisos viraram eventos no
RabbitMQ (`eventos`), e quem fez a requisição vem do token (`Logado`: id e perfil).

Novidade: cada ação fica registrada no histórico do chamado (a linha do tempo).

Permissões:
- solicitante: abre chamados e só vê, comenta e fecha os próprios;
- técnico e admin: veem todos, atribuem e mudam o status.
"""
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import clientes, eventos, repositorio
from app.erros import NaoEncontrado, RegraDeNegocio, SemPermissao
from app.esquemas import ChamadoCriar, ComentarioCriar
from app.modelos import Chamado, Comentario, Historico
from app.seguranca import Logado

# Prazo para resolver o chamado, conforme a prioridade (SLA)
HORAS_SLA = {"critica": 4, "alta": 8, "media": 24, "baixa": 72}

# De qual status para quais status um chamado pode ir
TRANSICOES = {
    "aberto": {"em_atendimento"},
    "em_atendimento": {"resolvido"},
    "resolvido": {"fechado", "em_atendimento"},  # reabrir se o problema voltar
    "fechado": set(),
}

ROTULOS = {"aberto": "aberto", "em_atendimento": "em atendimento", "resolvido": "resolvido", "fechado": "fechado"}
PRIORIDADES = {"baixa": "baixa", "media": "média", "alta": "alta", "critica": "crítica"}
EQUIPE = ("tecnico", "admin")


def eh_equipe(logado: Logado) -> bool:
    return logado.perfil in EQUIPE


def calcular_prazo(prioridade: str, inicio: datetime) -> datetime:
    return inicio + timedelta(hours=HORAS_SLA[prioridade])


def registrar(chamado: Chamado, autor_id: int, acao: str, descricao: str) -> None:
    """Acrescenta uma linha à linha do tempo do chamado."""
    chamado.historico.append(Historico(quando=datetime.now(), autor_id=autor_id, acao=acao, descricao=descricao[:200]))


def abrir(db: Session, dados: ChamadoCriar, logado: Logado, token: str) -> Chamado:
    ativo = clientes.obter_ativo(dados.ativo_id, token) if dados.ativo_id is not None else None  # HTTP

    agora = datetime.now()
    chamado = Chamado(**dados.model_dump(), solicitante_id=logado.id, status="aberto", criado_em=agora,
                      prazo_sla=calcular_prazo(dados.prioridade, agora))
    equipamento = f", equipamento {ativo['patrimonio']}" if ativo else ""
    registrar(chamado, logado.id, "aberto", f"Chamado aberto com prioridade {PRIORIDADES[dados.prioridade]}{equipamento}")
    chamado = repositorio.salvar(db, chamado)
    eventos.enviar("ChamadoAberto", logado.id,                                   # evento no RabbitMQ
                   f"Seu chamado #{chamado.id} foi aberto. Prazo: {chamado.prazo_sla:%d/%m %H:%M}.", chamado.id)
    return chamado


def obter(db: Session, chamado_id: int, logado: Logado) -> Chamado:
    chamado = repositorio.buscar_por_id(db, chamado_id)
    # Para quem não pode ver, responde "não encontrado": não revela que o chamado existe
    if chamado is None or not (eh_equipe(logado) or chamado.solicitante_id == logado.id):
        raise NaoEncontrado(f"Chamado {chamado_id} não encontrado.")
    return chamado


def listar(db: Session, logado: Logado, status: str | None = None, tecnico_id: int | None = None) -> list[Chamado]:
    solicitante_id = None if eh_equipe(logado) else logado.id
    return repositorio.listar(db, status, tecnico_id, solicitante_id)


def atribuir(db: Session, chamado_id: int, tecnico_id: int, logado: Logado, token: str) -> Chamado:
    if not eh_equipe(logado):
        raise SemPermissao("Só técnicos e administradores atribuem chamados.")
    chamado = obter(db, chamado_id, logado)
    if chamado.status in ("resolvido", "fechado"):
        raise RegraDeNegocio("Não é possível atribuir um chamado resolvido ou fechado.")
    tecnico = clientes.obter_tecnico(tecnico_id, token)                          # HTTP
    chamado.tecnico_id = tecnico["id"]
    iniciou = chamado.status == "aberto"
    if iniciou:
        chamado.status = "em_atendimento"
    registrar(chamado, logado.id, "atribuido",
              f"Atribuído a {tecnico['nome']}" + (" e atendimento iniciado" if iniciou else ""))
    repositorio.salvar(db, chamado)
    eventos.enviar("ChamadoAtribuido", tecnico["id"], f"O chamado #{chamado.id} foi atribuído a você.", chamado.id)
    return chamado


def mudar_status(db: Session, chamado_id: int, novo_status: str, logado: Logado) -> Chamado:
    chamado = obter(db, chamado_id, logado)
    # O solicitante só pode confirmar (fechar) ou reabrir o próprio chamado resolvido
    pode_solicitante = chamado.status == "resolvido" and novo_status in ("fechado", "em_atendimento")
    if not (eh_equipe(logado) or pode_solicitante):
        raise SemPermissao("Você não pode mudar o status deste chamado.")
    if novo_status not in TRANSICOES[chamado.status]:
        raise RegraDeNegocio(f"Não é possível ir de '{chamado.status}' para '{novo_status}'.")
    if novo_status == "em_atendimento" and chamado.tecnico_id is None:
        raise RegraDeNegocio("Atribua um técnico antes de iniciar o atendimento.")
    registrar(chamado, logado.id, "status", f"Status: {ROTULOS[chamado.status]} → {ROTULOS[novo_status]}")
    chamado.status = novo_status
    repositorio.salvar(db, chamado)
    if novo_status == "resolvido":
        eventos.enviar("ChamadoResolvido", chamado.solicitante_id,
                       f"Seu chamado #{chamado.id} foi resolvido. Confirme se está tudo certo.", chamado.id)
    return chamado


def comentar(db: Session, chamado_id: int, dados: ComentarioCriar, logado: Logado) -> Comentario:
    chamado = obter(db, chamado_id, logado)
    if chamado.status == "fechado":
        raise RegraDeNegocio("Chamados fechados não recebem comentários.")
    registrar(chamado, logado.id, "comentario", "Comentário adicionado")
    return repositorio.salvar_comentario(db, Comentario(
        chamado_id=chamado.id, autor_id=logado.id, texto=dados.texto, criado_em=datetime.now()
    ))


def painel(db: Session, logado: Logado) -> dict:
    chamados = listar(db, logado)
    agora = datetime.now()
    atrasados = sum(1 for c in chamados if c.status in ("aberto", "em_atendimento") and c.prazo_sla < agora)
    return {"total": len(chamados), "por_status": dict(Counter(c.status for c in chamados)), "atrasados": atrasados}
