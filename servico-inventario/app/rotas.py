from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import servico
from app.database import get_db
from app.esquemas import AtivoCriar, AtivoSaida
from app.seguranca import exigir_perfil, usuario_logado

router = APIRouter(prefix="/ativos", tags=["Inventário"])


@router.post("", response_model=AtivoSaida, status_code=201, dependencies=[Depends(exigir_perfil("tecnico", "admin"))])
def criar_ativo(dados: AtivoCriar, db: Session = Depends(get_db)):
    return servico.criar(db, dados)


@router.get("", response_model=list[AtivoSaida], dependencies=[Depends(usuario_logado)])
def listar_ativos(setor: str | None = Query(None, max_length=80), db: Session = Depends(get_db)):
    return servico.listar(db, setor)


@router.get("/{ativo_id}", response_model=AtivoSaida, dependencies=[Depends(usuario_logado)])
def obter_ativo(ativo_id: int, db: Session = Depends(get_db)):
    """O serviço de Chamados chama esta rota para conferir o equipamento antes de abrir um chamado."""
    return servico.obter(db, ativo_id)
