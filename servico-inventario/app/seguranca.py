"""Conferência do login neste serviço (cada serviço tem a sua cópia deste arquivo).

O token é assinado pelo serviço de Usuários com a chave privada (RS256). Aqui só se confere a
assinatura, com a chave pública que Usuários publica em GET /auth/chave-publica. Com a chave
pública dá para conferir um token, mas não para criar um: nenhum outro serviço consegue se passar
pelo serviço de Usuários.

A chave é buscada na primeira vez que alguém chama o serviço e guardada por alguns minutos. Se o
serviço de Usuários estiver fora do ar, segue valendo a última chave conhecida.
"""
import os
import threading
import time
from dataclasses import dataclass

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

USUARIOS_URL = os.getenv("USUARIOS_URL", "http://usuarios:8000")
CHAVE_VALIDADE_SEGUNDOS = int(os.getenv("CHAVE_VALIDADE_SEGUNDOS", "300"))
EMISSOR = "helpdesk-ti"


@dataclass(frozen=True)
class Logado:
    """Quem fez a requisição, segundo o token."""
    id: int
    perfil: str


_chave: dict = {"pem": None, "buscada_em": 0.0}
_trava = threading.Lock()


def chave_publica() -> str:
    with _trava:
        if _chave["pem"] and time.monotonic() - _chave["buscada_em"] < CHAVE_VALIDADE_SEGUNDOS:
            return _chave["pem"]
        for espera in (0, 0.5, 1.0):  # três tentativas, esperando um pouco mais a cada uma
            time.sleep(espera)
            try:
                resposta = httpx.get(f"{USUARIOS_URL}/auth/chave-publica", timeout=2)
                resposta.raise_for_status()
                _chave.update(pem=resposta.json()["chave_publica"], buscada_em=time.monotonic())
                return _chave["pem"]
            except (httpx.HTTPError, KeyError, ValueError):
                continue
        if _chave["pem"]:
            _chave["buscada_em"] = time.monotonic()  # segue com a última chave e só tenta de novo mais tarde
            return _chave["pem"]
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                        "Não foi possível conferir o login agora: o serviço de Usuários não respondeu.")


esquema = HTTPBearer(auto_error=False)

NAO_AUTENTICADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Faça login para continuar.",
    headers={"WWW-Authenticate": "Bearer"},
)


def usuario_logado(credenciais: HTTPAuthorizationCredentials | None = Depends(esquema)) -> Logado:
    if credenciais is None or credenciais.scheme.lower() != "bearer":
        raise NAO_AUTENTICADO
    try:
        dados = jwt.decode(
            credenciais.credentials, chave_publica(), algorithms=["RS256"], issuer=EMISSOR,
            options={"require": ["exp", "iat", "sub", "iss", "perfil"]},
        )
        return Logado(int(dados["sub"]), str(dados["perfil"]))
    except (jwt.PyJWTError, ValueError):
        raise NAO_AUTENTICADO


def token_bruto(credenciais: HTTPAuthorizationCredentials | None = Depends(esquema),
                logado: Logado = Depends(usuario_logado)) -> str:
    """O token já conferido, para repassar quando este serviço chama outro."""
    return credenciais.credentials


def exigir_perfil(*perfis: str):
    """Libera a rota só para os perfis informados."""
    def verificar(logado: Logado = Depends(usuario_logado)) -> Logado:
        if logado.perfil not in perfis:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Você não tem permissão para esta ação.")
        return logado
    return verificar
