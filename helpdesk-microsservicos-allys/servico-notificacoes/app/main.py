"""Serviço de Notificações: consome os eventos de Chamados e mostra os avisos de cada usuário."""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import consumidor
from app.config import DOCS_ATIVA
from app.database import Base, engine, get_db
from app.rotas import router
from app.seguranca_http import CabecalhosDeSeguranca

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s", datefmt="%H:%M:%S")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    Base.metadata.create_all(engine)
    consumidor.iniciar()
    yield
    consumidor.parar()


app = FastAPI(
    title="HelpDesk TI · Notificações", lifespan=ciclo_de_vida,
    docs_url="/docs" if DOCS_ATIVA else None, redoc_url=None,
    openapi_url="/openapi.json" if DOCS_ATIVA else None,
)
app.add_middleware(CabecalhosDeSeguranca)
app.include_router(router)


@app.get("/saude", tags=["Saúde"])
def saude(db: Session = Depends(get_db)):
    """Usada pelo healthcheck do Docker: só responde 200 se o banco também responder."""
    db.execute(text("SELECT 1"))
    return {"servico": "notificacoes", "banco": "ok"}
