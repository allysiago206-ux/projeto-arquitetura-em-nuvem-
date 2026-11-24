"""Serviço de Usuários: cadastro, login e emissão dos tokens."""
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import chaves, dados_exemplo
from app.config import DOCS_ATIVA
from app.database import Base, SessionLocal, engine, get_db
from app.erros import NaoEncontrado, RegraDeNegocio, SemPermissao
from app.rotas import router
from app.rotas_auth import router as router_auth
from app.seguranca_http import CabecalhosDeSeguranca


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        chaves.preparar(db)
        if os.getenv("DADOS_EXEMPLO", "1") == "1":
            dados_exemplo.carregar(db)
    yield


app = FastAPI(
    title="HelpDesk TI · Usuários", lifespan=ciclo_de_vida,
    docs_url="/docs" if DOCS_ATIVA else None, redoc_url=None,
    openapi_url="/openapi.json" if DOCS_ATIVA else None,
)
app.add_middleware(CabecalhosDeSeguranca)
app.include_router(router_auth)
app.include_router(router)


@app.exception_handler(NaoEncontrado)
def tratar_nao_encontrado(request: Request, erro: NaoEncontrado):
    return JSONResponse(status_code=404, content={"detail": str(erro)})


@app.exception_handler(RegraDeNegocio)
def tratar_regra(request: Request, erro: RegraDeNegocio):
    return JSONResponse(status_code=422, content={"detail": str(erro)})


@app.exception_handler(SemPermissao)
def tratar_sem_permissao(request: Request, erro: SemPermissao):
    return JSONResponse(status_code=403, content={"detail": str(erro)})


@app.exception_handler(IntegrityError)
def tratar_conflito(request: Request, erro: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "O registro conflita com outro já existente."})


@app.get("/saude", tags=["Saúde"])
def saude(db: Session = Depends(get_db)):
    """Usada pelo healthcheck do Docker: só responde 200 se o banco também responder."""
    db.execute(text("SELECT 1"))
    return {"servico": "usuarios", "banco": "ok"}
