"""O fluxo de um chamado: as regras do monólito, agora com consultas pela rede e o histórico."""
from datetime import datetime

from app.modelos import Chamado, Comentario, Historico


def test_abrir_calcula_sla_publica_evento_e_comeca_o_historico(abrir, enviados):
    r = abrir(prioridade="critica")
    assert r.status_code == 201
    c = r.json()
    horas = (datetime.fromisoformat(c["prazo_sla"]) - datetime.fromisoformat(c["criado_em"])).total_seconds() / 3600
    assert round(horas) == 4 and c["solicitante_id"] == 2
    assert enviados == [("ChamadoAberto", 2)]
    assert [h["descricao"] for h in c["historico"]] == ["Chamado aberto com prioridade crítica, equipamento PAT-1"]


def test_abrir_com_ativo_inexistente(abrir):
    r = abrir(ativo_id=999)
    assert r.status_code == 404 and r.json()["detail"] == "Equipamento 999 não encontrado no inventário."


def test_abrir_sem_equipamento_nao_consulta_o_inventario(abrir, rede):
    assert abrir(ativo_id=None).status_code == 201
    assert rede.tentativas["inventario"] == 0


def test_atribuir_confere_o_tecnico_e_registra(cliente, contas, abrir, enviados):
    cid = abrir().json()["id"]
    r = cliente.patch(f"/chamados/{cid}/atribuir", headers=contas["carla"], json={"tecnico_id": 4}).json()
    assert r["status"] == "em_atendimento" and r["tecnico_id"] == 4
    assert enviados[-1] == ("ChamadoAtribuido", 4)
    assert r["historico"][-1]["descricao"] == "Atribuído a Carla Dias e atendimento iniciado"


def test_so_tecnico_pode_ser_atribuido(cliente, contas, abrir):
    cid = abrir().json()["id"]
    r = cliente.patch(f"/chamados/{cid}/atribuir", headers=contas["carla"], json={"tecnico_id": 2})
    assert r.status_code == 422 and r.json()["detail"] == "Usuário 2 não é técnico."


def test_fluxo_completo_com_a_linha_do_tempo(cliente, contas, abrir, enviados):
    cid = abrir().json()["id"]
    cliente.patch(f"/chamados/{cid}/atribuir", headers=contas["carla"], json={"tecnico_id": 4})
    cliente.post(f"/chamados/{cid}/comentarios", headers=contas["carla"], json={"texto": "Trocando a fonte."})
    cliente.patch(f"/chamados/{cid}/status", headers=contas["carla"], json={"status": "resolvido"})
    r = cliente.patch(f"/chamados/{cid}/status", headers=contas["ana"], json={"status": "fechado"}).json()
    assert r["status"] == "fechado"
    assert ("ChamadoResolvido", 2) in enviados
    assert [h["acao"] for h in r["historico"]] == ["aberto", "atribuido", "comentario", "status", "status"]
    assert r["historico"][-1]["descricao"] == "Status: resolvido → fechado" and r["historico"][-1]["autor_id"] == 2


def test_transicao_invalida(cliente, contas, abrir):
    cid = abrir().json()["id"]
    assert cliente.patch(f"/chamados/{cid}/status", headers=contas["carla"], json={"status": "fechado"}).status_code == 422


def test_iniciar_atendimento_sem_tecnico(cliente, contas, abrir):
    cid = abrir().json()["id"]
    assert cliente.patch(f"/chamados/{cid}/status", headers=contas["carla"], json={"status": "em_atendimento"}).status_code == 422


def test_comentar_usa_o_usuario_logado(cliente, contas, abrir):
    cid = abrir().json()["id"]
    r = cliente.post(f"/chamados/{cid}/comentarios", headers=contas["carla"], json={"texto": "Verificando a fonte."})
    assert r.status_code == 201 and r.json()["autor_id"] == 4
    assert len(cliente.get(f"/chamados/{cid}", headers=contas["ana"]).json()["comentarios"]) == 1


def test_painel(cliente, contas, abrir):
    abrir()
    abrir(prioridade="baixa")
    p = cliente.get("/chamados/painel", headers=contas["carla"]).json()
    assert p["total"] == 2 and p["por_status"] == {"aberto": 2}


def test_sem_chave_estrangeira_para_outros_servicos():
    """Requisito 2: as tabelas só apontam para tabelas deste mesmo serviço."""
    alvos = {fk.column.table.name for t in (Chamado.__table__, Comentario.__table__, Historico.__table__) for fk in t.foreign_keys}
    assert alvos == {"chamados"}
