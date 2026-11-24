# O que foi implementado, e como

Este documento explica cada parte da versão em microsserviços: o que o desafio pedia, a forma
escolhida para resolver e onde está no código. O [README](README.md) mostra como rodar e as
decisões em resumo; aqui está o "como" de cada uma.

A ideia que guia esta versão: **cada peça é de verdade independente, e a infraestrutura trabalha a
favor disso.** O gateway é um Nginx que não sabe nada de Python, cada banco só é alcançável pelo
serviço dono, o login é conferido com uma chave que não permite criar tokens, e a fila guarda o
que não pôde ser entregue.

---

## 1. Os requisitos do desafio, um por um

| # | O desafio pede | Onde está resolvido |
|---|---|---|
| 1 | Três serviços separados, cada um num contêiner, que sobe sozinho | `servico-usuarios/`, `servico-inventario/`, `servico-chamados/` (e `servico-notificacoes/`, do bônus). Cada pasta é um projeto inteiro, com `app/`, `tests/`, `requirements.txt` e `Dockerfile` |
| 2 | Um banco por serviço, sem chave estrangeira entre serviços | Um PostgreSQL por serviço no `docker-compose.yml`, cada um numa rede só dele. Em `servico-chamados/app/modelos.py`, `solicitante_id`, `tecnico_id` e `ativo_id` são números simples |
| 3 | Chamados confere técnico e equipamento por HTTP | `servico-chamados/app/clientes.py`: `GET /usuarios/{id}` e `GET /ativos/{id}` |
| 4 | Serviço fora do ar: erro claro, com tempo limite | `clientes.py`: prazo por tentativa, 3 tentativas e um 503 que diz o que houve. No gateway, um 503 em JSON |
| 5 | API Gateway na porta 8000, com a tela funcionando por ele | `gateway/nginx.conf` e `gateway/web/` |
| 6 | Tudo sobe com `docker compose up --build` | `docker-compose.yml`: dez contêineres, sem nenhum ajuste manual |
| 7 | As mesmas funcionalidades e regras | `servico-chamados/app/servico.py`: SLA, transições de status e permissões iguais às do monólito |
| 8 | Segurança mantida | Cada serviço confere o token; permissões por perfil; o token é repassado nas chamadas; só o gateway tem porta; testes de segurança em cada serviço. Detalhes em [SECURITY.md](SECURITY.md) |
| 9 | README com diagrama, como rodar e decisões | [README.md](README.md) |
| Bônus | Notificações por evento | RabbitMQ, com `servico-notificacoes/` consumindo a fila |
| Bônus | Testes por serviço no GitHub Actions | `.github/workflows/testes.yml`: um job por serviço, e mais um para o gateway |
| Bônus | Rota de saúde | `GET /saude` em cada serviço, que também consulta o banco, usada pelos *healthchecks* do Docker |

---

## 2. As melhorias, e como cada uma foi feita

### 2.1 Gateway em Nginx (`gateway/nginx.conf`)

Em vez de escrever um gateway em Python, o gateway é **só configuração**:

- Cada prefixo de rota vai para um serviço: `/auth` e `/usuarios` para Usuários, `/ativos` para
  Inventário, `/chamados` para Chamados, `/notificacoes` para Notificações. Qualquer outro caminho
  recebe 404 sem chegar a nenhum serviço.
- O endereço de cada serviço fica numa variável (`set $destino http://inventario:8000`) e o Nginx usa
  o DNS do Docker (`resolver 127.0.0.11 valid=10s`). Com isso, **o nome é consultado de novo a cada
  10 segundos**. Sem esse cuidado, o Nginx consultaria só ao subir e não subiria se algum serviço
  estivesse parado.
- Quando um serviço não responde, o próprio Nginx devolve **503 em JSON**: "O serviço de inventário
  está fora do ar. Tente novamente em alguns segundos." (blocos `error_page` e `@fora_do_ar`).
- **Limite de requisições por endereço** (`limit_req`): 20 por segundo no geral e **10 por minuto no
  login**. Quem tenta adivinhar senhas recebe 429 antes de ocupar o serviço de Usuários.
- Corpo da requisição limitado a **64 KB** (`client_max_body_size`), **cabeçalhos de segurança** em
  todas as respostas (CSP, `X-Frame-Options`…), **cookies descartados** na ida e na volta, e o
  `X-Forwarded-For` preenchido com o endereço que o Nginx viu. O que o navegador mandar nesse
  cabeçalho é ignorado.
- Roda com a imagem `nginx-unprivileged`: **sem root** e com o disco só de leitura.

### 2.2 Login com chave privada e chave pública (RS256)

No monólito, um segredo (`JWT_SEGREDO`) assinava e conferia os tokens. Com quatro serviços, esse
segredo teria de estar nos quatro, e **qualquer um deles poderia fabricar um token** de administrador.

Aqui o token é assinado com um **par de chaves**:

- A **chave privada** fica só no serviço de Usuários (`servico-usuarios/app/chaves.py`). É a única
  que cria tokens.
- A **chave pública** é publicada em `GET /auth/chave-publica`. Com ela dá para **conferir** um token,
  mas não para criar um.
- Os outros três serviços buscam a chave pública na primeira vez que precisam, guardam por 5 minutos e
  conferem a assinatura sozinhos (`app/seguranca.py`, uma cópia em cada serviço). Se Usuários estiver
  fora do ar, seguem com a última chave conhecida.
- **De onde vem a chave privada:** da variável `JWT_CHAVE_PRIVADA` (`.env`), se existir. Se não, o
  serviço gera uma na primeira subida e a **guarda no próprio banco**, na tabela `chave_assinatura`.
  Assim tudo sobe sem passo manual, a chave não muda a cada reinício, e nada fica no código.
- A variável chega **só ao contêiner de Usuários**: no `docker-compose.yml`, ela não vai para os outros.
- Há um teste para o ataque clássico contra RS256, a **troca de algoritmo**: alguém assina em HS256
  usando a chave pública (que é pública) como segredo. O serviço recusa, porque só aceita RS256
  (`servico-usuarios/tests/test_seguranca.py`).

### 2.3 Um PostgreSQL por serviço, cada um na sua rede

- Quatro contêineres `postgres:17.6-alpine`, cada um com o seu volume (`dados-usuarios`,
  `dados-inventario`, `dados-chamados`, `dados-notificacoes`).
- **Cada banco fica numa rede só dele** (`rede-usuarios`, `rede-inventario`…), marcada como `internal`,
  junto com o serviço dono. O serviço de Chamados **nem encontra** o nome `banco-usuarios`. Assim, a
  regra "nenhum serviço lê o banco de outro" não depende de disciplina: a rede não deixa.
- Por isso o banco aceita conexão sem senha (`POSTGRES_HOST_AUTH_METHOD: trust`): só o dono alcança.
  Em produção, cada banco teria usuário e senha próprios.
- Os bancos rodam sem root, com o disco só de leitura (os dados ficam no volume).

### 2.4 Chamadas entre serviços: novas tentativas e prazo (`servico-chamados/app/clientes.py`)

Quando Chamados consulta Usuários ou Inventário:

1. **Prazo por tentativa de 1 segundo**, contando tudo, até a busca do nome do serviço na rede. O tempo
   limite do próprio httpx não cobre essa busca, e com um contêiner parado ela levava 4 segundos.
2. **Até 3 tentativas, com espera crescente**: 0,2 s, depois 0,4 s. Uma falha passageira, como o serviço
   reiniciando, se resolve na segunda tentativa, e o usuário nem percebe.
3. **Erro claro no fim**: 503, com a mensagem "Inventário indisponível no momento (3 tentativas sem
   resposta). Tente novamente em alguns segundos." e o cabeçalho `Retry-After: 5`.
4. Respostas que não mudam com outra tentativa (404, 401, 422) **não são repetidas**.
5. O token do usuário é **repassado** (`Authorization`), e o outro serviço confere de novo.

Cada tentativa aparece no log de Chamados: `inventário: tentativa 2 de 3 falhou (sem resposta em 1.0 s)`.

### 2.5 Eventos no RabbitMQ (`servico-chamados/app/eventos.py` e `servico-notificacoes/app/consumidor.py`)

- Chamados publica `ChamadoAberto`, `ChamadoAtribuido` e `ChamadoResolvido` na exchange **`helpdesk`**
  (do tipo *topic*), com as rotas `chamado.aberto`, `chamado.atribuido` e `chamado.resolvido`.
- A fila **`notificacoes`** é **durável** e recebe tudo o que começa com `chamado.`. As mensagens são
  **persistentes**: com o serviço de Notificações parado, ou até com o RabbitMQ reiniciando, elas esperam.
- O publicador pede **confirmação** ao RabbitMQ (`confirm_delivery`) e tenta até 3 vezes. A publicação
  roda **em segundo plano**, numa fila de uma thread só: quem abre o chamado não espera o RabbitMQ, e os
  eventos saem na ordem em que aconteceram.
- O consumidor confirma cada mensagem (**ack**) **só depois de gravar o aviso** no banco.
- **Fila de mensagens mortas:** uma mensagem que não dá para processar (fora do formato) é recusada sem
  voltar para a fila e vai para **`notificacoes.mortas`**. Assim ela não trava as outras e fica guardada
  para alguém examinar.
- Se o RabbitMQ cair, o consumidor tenta reconectar com espera crescente: 1 s, 2 s, 4 s… até 30 s.
- As filas são declaradas pelos dois lados (declarar de novo não muda nada). Um evento publicado antes
  de Notificações subir pela primeira vez já encontra a fila esperando.

### 2.6 Histórico do chamado (`servico-chamados/app/modelos.py`, classe `Historico`)

Cada chamado ganhou uma **linha do tempo**: abertura (com a prioridade e o equipamento), atribuição
(com o nome do técnico), cada mudança de status ("Status: em atendimento → resolvido") e cada
comentário. Cada linha guarda a data e quem fez. A API devolve o histórico junto com o chamado, e a
tela o mostra numa gaveta lateral, no botão **Histórico** de cada cartão.

### 2.7 *Healthchecks*: cada serviço só sobe quando o banco está pronto

- `GET /saude` de cada serviço executa um `SELECT 1` no banco: só responde 200 se o banco responder.
- O Docker usa essa rota para marcar o contêiner como **healthy** (`docker compose ps` mostra). Os bancos
  usam o `pg_isready`, e o RabbitMQ, o `rabbitmq-diagnostics ping`.
- No `docker-compose.yml`, cada serviço espera o banco dele ficar *healthy* antes de subir
  (`depends_on` com `condition: service_healthy`), e o gateway espera os quatro serviços.

### 2.8 A tela: quadro por status (`gateway/web/`)

- Um **quadro com quatro colunas**: Abertos, Em atendimento, Resolvidos e Fechados, com a contagem em
  cada uma. Cada chamado é um cartão com a prioridade na borda colorida, o solicitante, o técnico, o
  prazo e as ações.
- O formulário de **novo chamado** abre por um botão. Os **avisos** e o **histórico** abrem em gavetas
  laterais. Os erros aparecem num **recado** no canto da tela, que some sozinho.
- A lista de equipamentos é carregada **uma vez por sessão**: se o Inventário cair depois, ela continua
  lá, e dá para tentar abrir um chamado com equipamento e ver o erro claro.
- Segurança: todo texto da API passa por `esc()` antes de entrar no HTML, não há script embutido e a CSP
  só permite arquivos do próprio servidor. Acessibilidade: foco visível, rótulo em todos os campos e `Esc`
  fecha as gavetas.

### 2.9 Cada serviço é um projeto inteiro

Não há biblioteca comum entre os serviços. A conferência do token (`app/seguranca.py`) está copiada em
Inventário, Chamados e Notificações. É uma escolha consciente: cada pasta pode ir para outro repositório
ou outro time sem levar nada junto. O preço é a duplicação, e uma mudança nessa regra precisa ser feita
nos três.

### 2.10 Testes por serviço no GitHub Actions (`.github/workflows/testes.yml`)

- Uma **matriz** com um job por serviço: cada job instala só as dependências daquele serviço, roda os
  testes dele e confere as dependências com o `pip-audit`. Se um quebrar, os outros seguem, e o resultado
  mostra qual foi.
- Um job para o gateway: `nginx -t` valida a configuração, e os testes da tela conferem o escape do HTML,
  os cabeçalhos e as rotas.

---

## 3. Como conferir que está tudo funcionando

```bash
docker compose up --build -d     # sobe os dez contêineres
docker compose ps                # todos "healthy"; só o gateway mostra porta (127.0.0.1:8000)
curl -i http://localhost:8000/chamados          # 401: sem login
docker compose stop inventario   # a lista de chamados continua; abrir com equipamento dá o 503 claro
docker compose logs chamados     # as três tentativas, uma por linha
docker compose start inventario
docker compose stop notificacoes # abra um chamado: o aviso espera na fila
docker compose exec rabbitmq rabbitmqctl list_queues name messages   # a fila notificacoes com 1 mensagem
docker compose start notificacoes                                    # o aviso chega
```

Testes de um serviço (dentro da pasta dele):

```bash
pip install -r requirements.txt pytest httpx
pytest -q
```

---

## 4. Para subir no GitHub

O desafio pede um repositório público com o nome `helpdesk-microsservicos-<seu-nome>` e avalia o
histórico: **commits ao longo do trabalho, um serviço por vez, com mensagens claras**.

1. Crie o repositório vazio no GitHub (sem README, sem `.gitignore` e sem licença).
2. Nesta pasta: `git init`, configure o seu nome e e-mail (`git config user.name` e `git config user.email`)
   e aponte para o repositório (`git remote add origin <link>`).
3. Uma ordem de commits que acompanha o trabalho, uma parte por vez:
   1. `servico-usuarios/`: login com RS256, chave guardada no banco
   2. `servico-inventario/`
   3. `servico-chamados/`: chamadas HTTP com novas tentativas e o histórico
   4. `servico-notificacoes/` e `rabbitmq/`: eventos com fila durável e fila de mortas
   5. `gateway/`: Nginx e a tela em quadro
   6. `docker-compose.yml`, `.env.example` e `.gitignore`: bancos em redes próprias e *healthchecks*
   7. `.github/`: testes por serviço e Dependabot
   8. `README.md`, `IMPLEMENTACAO.md`, `SECURITY.md`, `DESAFIO.md` e `docs/`
4. Depois de gravar o vídeo, cole o link no topo do README e faça um último commit.
