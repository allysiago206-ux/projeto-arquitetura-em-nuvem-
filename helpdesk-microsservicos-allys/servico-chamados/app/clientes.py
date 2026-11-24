"""Consultas aos serviços de Usuários e Inventário, pela rede.

No monólito, conferir o técnico e o equipamento era uma chamada de função. Agora é uma requisição
HTTP, que pode falhar por um instante: o serviço reiniciando, a rede piscando. Por isso cada
consulta segue três regras:

1. prazo por tentativa (PRAZO_POR_TENTATIVA): conta tudo, inclusive a busca do nome do serviço na
   rede, que o tempo limite do httpx não cobre;
2. novas tentativas com espera crescente (backoff): espera 0,2 s, depois 0,4 s, até TENTATIVAS vezes.
   Uma falha passageira se resolve sozinha, sem o usuário perceber;
3. erro claro no fim: 503, dizendo quantas tentativas foram feitas.

Respostas que não mudam com outra tentativa (404, 401, 422) não são repetidas.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as PrazoEsgotado

import httpx

from app.config import ESPERA_INICIAL, INVENTARIO_URL, PRAZO_POR_TENTATIVA, TENTATIVAS, USUARIOS_URL
from app.erros import NaoEncontrado, RegraDeNegocio, ServicoIndisponivel

log = logging.getLogger("chamados.clientes")

# ponytail: uma tentativa que estoura o prazo segue na thread até a rede desistir; 16 threads bastam aqui
_consultas = ThreadPoolExecutor(max_workers=16, thread_name_prefix="consulta")


def _consultar(servico: str, url: str, token: str) -> httpx.Response:
    espera = ESPERA_INICIAL
    for tentativa in range(1, TENTATIVAS + 1):
        pedido = _consultas.submit(httpx.get, url, headers={"Authorization": f"Bearer {token}"}, timeout=PRAZO_POR_TENTATIVA)
        try:
            resposta = pedido.result(timeout=PRAZO_POR_TENTATIVA)
            if resposta.status_code < 500:
                return resposta
            motivo = f"respondeu {resposta.status_code}"
        except PrazoEsgotado:
            motivo = f"sem resposta em {PRAZO_POR_TENTATIVA:.1f} s"
        except httpx.TransportError as erro:
            motivo = type(erro).__name__
        log.warning("%s: tentativa %d de %d falhou (%s)", servico, tentativa, TENTATIVAS, motivo)
        if tentativa < TENTATIVAS:
            time.sleep(espera)
            espera *= 2
    raise ServicoIndisponivel(
        f"{servico.capitalize()} indisponível no momento ({TENTATIVAS} tentativas sem resposta). "
        "Tente novamente em alguns segundos."
    )


def obter_ativo(ativo_id: int, token: str) -> dict:
    """Era inventario.servico.obter(): agora é GET /ativos/{id} no serviço de Inventário."""
    resposta = _consultar("inventário", f"{INVENTARIO_URL}/ativos/{ativo_id}", token)
    if resposta.status_code == 404:
        raise NaoEncontrado(f"Equipamento {ativo_id} não encontrado no inventário.")
    if resposta.status_code != 200:
        raise RegraDeNegocio(f"O inventário recusou a consulta ({resposta.status_code}).")
    return resposta.json()


def obter_tecnico(usuario_id: int, token: str) -> dict:
    """Era usuarios.servico.obter_tecnico(): agora é GET /usuarios/{id} no serviço de Usuários."""
    resposta = _consultar("usuários", f"{USUARIOS_URL}/usuarios/{usuario_id}", token)
    if resposta.status_code == 404:
        raise NaoEncontrado(f"Usuário {usuario_id} não encontrado.")
    if resposta.status_code != 200:
        raise RegraDeNegocio(f"O serviço de usuários recusou a consulta ({resposta.status_code}).")
    usuario = resposta.json()
    if usuario["perfil"] != "tecnico":
        raise RegraDeNegocio(f"Usuário {usuario_id} não é técnico.")
    return usuario
