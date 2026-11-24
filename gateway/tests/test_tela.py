"""Segurança da tela e do gateway, conferida nos próprios arquivos (o Nginx não roda em Python)."""
import re
from pathlib import Path

GATEWAY = Path(__file__).parent.parent


def ler(caminho: str) -> str:
    return (GATEWAY / caminho).read_text(encoding="utf-8")


def test_tela_escapa_o_html():
    js = ler("web/app.js")
    assert "const esc =" in js and "onclick" not in js


def test_tela_sem_script_embutido():
    html = ler("web/index.html")
    assert re.findall(r"<script[^>]*>", html) == ['<script src="/app.js">']
    assert not re.search(r"\son[a-z]+\s*=", html)  # nenhum onclick=, onload=... no HTML


def test_gateway_tem_os_cabecalhos_e_os_limites():
    conf = ler("nginx.conf")
    for trecho in ("Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options",
                   "client_max_body_size 64k", "limit_req_zone", 'proxy_set_header Cookie ""',
                   "proxy_set_header X-Forwarded-For $remote_addr", "proxy_hide_header Set-Cookie"):
        assert trecho in conf, trecho


def test_gateway_so_encaminha_as_rotas_conhecidas():
    conf = ler("nginx.conf")
    destinos = set(re.findall(r"set \$destino (\S+);", conf))
    assert destinos == {"http://usuarios:8000", "http://inventario:8000", "http://chamados:8000", "http://notificacoes:8000"}
    assert 'return 404 \'{"detail": "Rota não encontrada."}\'' in conf
