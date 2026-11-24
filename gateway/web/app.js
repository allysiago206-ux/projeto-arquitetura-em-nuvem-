// Tela do HelpDesk: um quadro com uma coluna por status. Todo texto vindo da API passa por esc()
// antes de ir para o HTML, para impedir que um título como <script> seja executado (XSS).
"use strict";
const API = "";  // o Nginx serve a tela e a API no mesmo endereço
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (s) => new Date(s).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const COLUNAS = [["aberto", "Abertos"], ["em_atendimento", "Em atendimento"], ["resolvido", "Resolvidos"], ["fechado", "Fechados"]];
const PRIORIDADE = { baixa: "Baixa", media: "Média", alta: "Alta", critica: "Crítica" };

let token = null, eu = null, usuarios = [], ativos = null, chamados = [], tempoRecado = null;
try { token = sessionStorage.getItem("token"); } catch (e) { token = null; }

async function req(metodo, caminho, corpo) {
  const cab = { "Content-Type": "application/json" };
  if (token) cab.Authorization = "Bearer " + token;
  const r = await fetch(API + caminho, { method: metodo, headers: cab, body: corpo ? JSON.stringify(corpo) : undefined });
  const dados = await r.json().catch(() => ({}));
  if (r.status === 401 && caminho !== "/auth/login") { sair(); throw new Error("Sessão expirada. Entre novamente."); }
  if (!r.ok) throw new Error(typeof dados.detail === "string" ? dados.detail : "Dados inválidos (" + r.status + ").");
  return dados;
}

// O recado aparece no canto da tela e some sozinho
function recado(mensagem) {
  $("recado").textContent = mensagem;
  $("recado").hidden = !mensagem;
  clearTimeout(tempoRecado);
  if (mensagem) tempoRecado = setTimeout(() => { $("recado").hidden = true; }, 7000);
}

function guardarToken(t) { token = t; try { t ? sessionStorage.setItem("token", t) : sessionStorage.removeItem("token"); } catch (e) {} }
function sair() { guardarToken(null); eu = null; ativos = null; mostrar(false); }
function mostrar(logado) {
  $("tela-login").hidden = logado; $("tela-sistema").hidden = !logado; $("barra").hidden = !logado;
  if (!logado) { $("painel-avisos").hidden = true; $("painel-historico").hidden = true; }
}
const nome = (id) => (usuarios.find((u) => u.id === id) || {}).nome || "—";
const equipe = () => eu && (eu.perfil === "tecnico" || eu.perfil === "admin");

async function carregar() {
  eu = await req("GET", "/auth/eu");
  $("quem").textContent = eu.nome;
  const falhas = [];
  const tentar = (caminho, padrao) => req("GET", caminho).catch((e) => { falhas.push(e.message); return padrao; });
  // Os equipamentos vêm uma vez por sessão: se o Inventário cair depois, a lista já está aqui
  const [lista, equipamentos, todos, painel, avisos] = await Promise.all([
    tentar("/usuarios", usuarios), ativos ? Promise.resolve(ativos) : tentar("/ativos", null), tentar("/chamados", []),
    tentar("/chamados/painel", { total: 0, por_status: {}, atrasados: 0 }), tentar("/notificacoes", []),
  ]);
  usuarios = lista; chamados = todos;
  if (equipamentos) {
    ativos = equipamentos;
    $("ativo").innerHTML = `<option value="">Nenhum</option>` + ativos.map((a) => `<option value="${esc(a.id)}">${esc(a.patrimonio)} · ${esc(a.descricao)}</option>`).join("");
  }
  $("resumo").innerHTML = `<b>${esc(painel.total)}</b> chamados` +
    (painel.atrasados ? ` · <span class="atrasados">${esc(painel.atrasados)} atrasado(s)</span>` : " · nenhum atrasado");
  const tecnicos = usuarios.filter((u) => u.perfil === "tecnico");
  $("quadro").innerHTML = COLUNAS.map(([status, titulo]) => {
    const daColuna = chamados.filter((c) => c.status === status);
    return `<section class="coluna" aria-labelledby="col-${status}">
      <h2 id="col-${status}">${esc(titulo)} <span class="quantos">${esc(painel.por_status[status] || 0)}</span></h2>
      ${daColuna.map((c) => cartao(c, tecnicos)).join("") || `<p class="vazio">Nada aqui.</p>`}
    </section>`;
  }).join("");
  $("contador").textContent = avisos.length;
  $("avisos").innerHTML = avisos.slice().reverse().map((a) =>
    `<div class="aviso"><b>${esc(a.tipo)}</b><span>${esc(a.mensagem)}</span><small>${esc(fmt(a.criada_em))}</small></div>`).join("") || "<p class=\"vazio\">Nenhum aviso.</p>";
  if (falhas.length) recado([...new Set(falhas)].join(" "));
}

function cartao(c, tecnicos) {
  return `<article class="cartao p-${esc(c.prioridade)}">
    <div class="cartao-topo"><span class="numero">#${esc(c.id)}</span><span class="prioridade">${esc(PRIORIDADE[c.prioridade])}</span></div>
    <h3>${esc(c.titulo)}</h3>
    <dl>
      <dt>Solicitante</dt><dd>${esc(nome(c.solicitante_id))}</dd>
      <dt>Técnico</dt><dd>${c.tecnico_id ? esc(nome(c.tecnico_id)) : "—"}</dd>
      <dt>Prazo</dt><dd>${esc(fmt(c.prazo_sla))}</dd>
    </dl>
    <div class="acoes">${acoes(c, tecnicos)}<button type="button" class="discreto" data-acao="historico" data-id="${esc(c.id)}">Histórico</button></div>
  </article>`;
}

function acoes(c, tecnicos) {
  const botao = (acao, texto) => `<button type="button" data-acao="${acao}" data-id="${esc(c.id)}">${esc(texto)}</button>`;
  if (equipe() && c.status === "aberto")
    return `<select id="t${esc(c.id)}" aria-label="Técnico para o chamado ${esc(c.id)}">${tecnicos.map((t) => `<option value="${esc(t.id)}">${esc(t.nome)}</option>`).join("")}</select>` + botao("atribuir", "Atribuir");
  if (equipe() && c.status === "em_atendimento") return botao("resolvido", "Resolver");
  if (c.status === "resolvido" && (equipe() || c.solicitante_id === eu.id)) return botao("fechado", "Fechar") + botao("em_atendimento", "Reabrir");
  return "";
}

function mostrarHistorico(id) {
  const c = chamados.find((x) => x.id === id);
  if (!c) return;
  $("t-historico").textContent = `Histórico do chamado #${c.id}`;
  $("linha-do-tempo").innerHTML = c.historico.map((h) =>
    `<li><time>${esc(fmt(h.quando))}</time><span>${esc(h.descricao)}</span><small>por ${esc(nome(h.autor_id))}</small></li>`).join("");
  $("painel-avisos").hidden = true;
  $("painel-historico").hidden = false;
}

async function acao(f) { try { await f(); await carregar(); } catch (e) { recado(e.message); } }

$("quadro").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-acao]");
  if (!b) return;
  const id = Number(b.dataset.id);
  if (b.dataset.acao === "historico") return mostrarHistorico(id);
  if (b.dataset.acao === "atribuir") acao(() => req("PATCH", `/chamados/${id}/atribuir`, { tecnico_id: Number($("t" + id).value) }));
  else acao(() => req("PATCH", `/chamados/${id}/status`, { status: b.dataset.acao }));
});

function alternarNovo(abrir) { $("novo").hidden = !abrir; $("mostrar-novo").setAttribute("aria-expanded", String(abrir)); if (abrir) $("titulo").focus(); }
$("mostrar-novo").addEventListener("click", () => alternarNovo($("novo").hidden));
$("cancelar-novo").addEventListener("click", () => alternarNovo(false));

$("novo").addEventListener("submit", (e) => {
  e.preventDefault();
  acao(async () => {
    await req("POST", "/chamados", {
      titulo: $("titulo").value, descricao: $("descricao").value, prioridade: $("prioridade").value,
      ativo_id: $("ativo").value ? Number($("ativo").value) : null,
    });
    alternarNovo(false);
  });
});

$("sino").addEventListener("click", () => {
  const abrir = $("painel-avisos").hidden;
  $("painel-historico").hidden = true;
  $("painel-avisos").hidden = !abrir;
  $("sino").setAttribute("aria-expanded", String(abrir));
});
document.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-fechar]");
  if (b) { $(b.dataset.fechar).hidden = true; $("sino").setAttribute("aria-expanded", "false"); }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { $("painel-avisos").hidden = true; $("painel-historico").hidden = true; }
});

$("tela-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("erro-login").textContent = "";
  try {
    const r = await req("POST", "/auth/login", { email: $("email").value, senha: $("senha").value });
    guardarToken(r.access_token); $("senha").value = "";
    mostrar(true); await carregar();
  } catch (err) { $("erro-login").textContent = err.message; }
});

$("sair").addEventListener("click", sair);

if (token) { mostrar(true); carregar().catch((e) => recado(e.message)); } else { mostrar(false); }
