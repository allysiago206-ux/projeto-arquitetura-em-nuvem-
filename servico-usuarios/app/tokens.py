"""Criação e conferência dos tokens JWT, assinados com a chave privada deste serviço (RS256)."""
from datetime import datetime, timedelta, timezone

import jwt

from app import chaves
from app.config import JWT_ALGORITMO, JWT_EMISSOR, TOKEN_MINUTOS


class TokenInvalido(Exception):
    pass


def criar(usuario_id: int, perfil: str) -> tuple[str, datetime]:
    agora = datetime.now(timezone.utc)
    expira = agora + timedelta(minutes=TOKEN_MINUTOS)
    dados = {"sub": str(usuario_id), "perfil": perfil, "iat": agora, "exp": expira, "iss": JWT_EMISSOR}
    return jwt.encode(dados, chaves.privada(), algorithm=JWT_ALGORITMO), expira


def ler(token: str) -> int:
    """Devolve o id do usuário do token, ou lança TokenInvalido."""
    try:
        dados = jwt.decode(
            token, chaves.publica(), algorithms=[JWT_ALGORITMO], issuer=JWT_EMISSOR,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
        return int(dados["sub"])
    except (jwt.PyJWTError, ValueError) as erro:
        raise TokenInvalido() from erro
