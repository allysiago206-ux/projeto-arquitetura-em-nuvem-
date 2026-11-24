from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import servico
from app.database import get_db
from app.esquemas import NotificacaoSaida
from app.seguranca import Logado, usuario_logado

router = APIRouter(prefix="/notificacoes", tags=["Notificações"])


@router.get("", response_model=list[NotificacaoSaida])
def minhas_notificacoes(logado: Logado = Depends(usuario_logado), db: Session = Depends(get_db)):
    """Cada usuário vê só as próprias notificações."""
    return servico.listar(db, logado.id)
