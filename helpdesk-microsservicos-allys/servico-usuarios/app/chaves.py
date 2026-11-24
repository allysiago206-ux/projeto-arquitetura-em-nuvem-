"""O par de chaves que assina os tokens (RS256).

No monólito, um segredo só (JWT_SEGREDO) assinava e conferia os tokens. Com quatro serviços, esse
segredo teria de ser copiado em todos, e qualquer um deles poderia fabricar tokens. Aqui:

- a chave **privada** fica só no serviço de Usuários, o único que emite tokens;
- a chave **pública** é publicada em GET /auth/chave-publica, e os outros serviços a usam para
  conferir a assinatura. Com ela, dá para conferir, mas não para criar um token.

A chave privada vem da variável JWT_CHAVE_PRIVADA (.env) ou, se ela não existir, é gerada na
primeira subida e guardada no banco deste serviço. Nunca no código.
"""
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.config import JWT_CHAVE_PRIVADA
from app.database import Base


class ChaveAssinatura(Base):
    __tablename__ = "chave_assinatura"

    id: Mapped[int] = mapped_column(primary_key=True)
    algoritmo: Mapped[str] = mapped_column(String(10))
    chave_privada_pem: Mapped[str] = mapped_column(Text)


_privada: str | None = None
_publica: str | None = None


def preparar(db: Session) -> None:
    """Carrega a chave privada do .env ou do banco; se não houver nenhuma, gera e guarda."""
    global _privada, _publica
    pem = JWT_CHAVE_PRIVADA.strip()
    if not pem:
        guardada = db.scalar(select(ChaveAssinatura).order_by(ChaveAssinatura.id.desc()))
        if guardada is None:
            nova = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            guardada = ChaveAssinatura(algoritmo="RS256", chave_privada_pem=nova.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            ).decode())
            db.add(guardada)
            db.commit()
        pem = guardada.chave_privada_pem
    chave = serialization.load_pem_private_key(pem.encode(), password=None)
    _privada = pem
    _publica = chave.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def privada() -> str:
    if _privada is None:
        raise RuntimeError("Chave de assinatura não carregada: chaves.preparar() roda ao iniciar o serviço.")
    return _privada


def publica() -> str:
    if _publica is None:
        raise RuntimeError("Chave de assinatura não carregada: chaves.preparar() roda ao iniciar o serviço.")
    return _publica
