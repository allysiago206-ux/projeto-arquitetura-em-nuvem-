from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import servico
from app.database import get_db
from app.esquemas import (
    Atribuicao, ChamadoCriar, ChamadoSaida, ComentarioCriar, ComentarioSaida, MudancaStatus, Painel, Status,
)
from app.seguranca import Logado, token_bruto, usuario_logado

router = APIRouter(prefix="/chamados", tags=["Chamados"])


@router.post("", response_model=ChamadoSaida, status_code=201)
def abrir_chamado(dados: ChamadoCriar, logado: Logado = Depends(usuario_logado), token: str = Depends(token_bruto),
                  db: Session = Depends(get_db)):
    return servico.abrir(db, dados, logado, token)


@router.get("", response_model=list[ChamadoSaida])
def listar_chamados(status: Status | None = None, tecnico_id: int | None = None,
                    logado: Logado = Depends(usuario_logado), db: Session = Depends(get_db)):
    return servico.listar(db, logado, status, tecnico_id)


@router.get("/painel", response_model=Painel)
def painel(logado: Logado = Depends(usuario_logado), db: Session = Depends(get_db)):
    return servico.painel(db, logado)


@router.get("/{chamado_id}", response_model=ChamadoSaida)
def obter_chamado(chamado_id: int, logado: Logado = Depends(usuario_logado), db: Session = Depends(get_db)):
    return servico.obter(db, chamado_id, logado)


@router.patch("/{chamado_id}/atribuir", response_model=ChamadoSaida)
def atribuir_chamado(chamado_id: int, dados: Atribuicao, logado: Logado = Depends(usuario_logado),
                     token: str = Depends(token_bruto), db: Session = Depends(get_db)):
    return servico.atribuir(db, chamado_id, dados.tecnico_id, logado, token)


@router.patch("/{chamado_id}/status", response_model=ChamadoSaida)
def mudar_status(chamado_id: int, dados: MudancaStatus, logado: Logado = Depends(usuario_logado),
                 db: Session = Depends(get_db)):
    return servico.mudar_status(db, chamado_id, dados.status, logado)


@router.post("/{chamado_id}/comentarios", response_model=ComentarioSaida, status_code=201)
def comentar(chamado_id: int, dados: ComentarioCriar, logado: Logado = Depends(usuario_logado),
             db: Session = Depends(get_db)):
    return servico.comentar(db, chamado_id, dados, logado)
