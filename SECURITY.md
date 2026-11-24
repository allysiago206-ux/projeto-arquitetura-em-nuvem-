# Segurança

Projeto didático, com práticas de segurança reais. A versão em microsserviços mantém o que o
monólito protegia e trata o que a rede trouxe: serviços que precisam confiar no login uns dos
outros, bancos separados e um ponto de entrada exposto.

## O que está protegido

| Risco | Proteção |
|---|---|
| Acesso sem login | Cada serviço confere o token antes de responder. Só `/auth/login`, `/auth/chave-publica`, `/saude` e a tela não exigem login. |
| Token falsificado | Token assinado com **RS256**. A chave privada fica só no serviço de Usuários; os outros conferem com a chave pública, que não serve para criar tokens. Aceita só RS256: `alg: none` e a troca para HS256 com a chave pública são recusados (há teste para os dois). |
| Chave de assinatura exposta | A chave privada vem do `.env` (e chega só ao contêiner de Usuários) ou é gerada na primeira subida e guardada no banco de Usuários. Nunca no código. |
| Senhas vazadas do banco | Hash **scrypt** com sal aleatório. A senha nunca é salva nem devolvida pela API. |
| Adivinhar senhas | Duas barreiras: o gateway limita o login a 10 tentativas por minuto por endereço, e o serviço de Usuários bloqueia por alguns minutos depois de 5 senhas erradas para o mesmo e-mail. A mensagem é a mesma para e-mail inexistente e senha errada. |
| Excesso de requisições | O gateway limita a 20 requisições por segundo por endereço e responde 429. |
| Ver ou mexer no que não é seu | Permissões por perfil em cada serviço: o solicitante só vê os próprios chamados e avisos; só técnicos e administradores atribuem e resolvem; só administradores criam usuários. |
| Agir em nome de outra pessoa | O solicitante e o autor vêm do token, não do corpo da requisição; campos extras são recusados. Quando Chamados consulta outro serviço, repassa o token do usuário, e lá ele é conferido de novo. |
| Um serviço lendo o banco de outro | Cada PostgreSQL fica numa rede interna só dele, com o serviço dono. Os outros contêineres nem encontram o nome daquele banco. |
| Serviços expostos | Só o gateway publica porta, e só em `127.0.0.1`. Serviços, bancos e RabbitMQ ficam em redes internas. |
| Cabeçalhos forjados | O gateway preenche o `X-Forwarded-For` com o endereço que ele viu e descarta cookies na ida e na volta. |
| XSS na tela | Todo texto da API é escapado antes de entrar no HTML; não há script embutido; a CSP só permite arquivos do próprio servidor. |
| Clickjacking e outros | `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` e `Permissions-Policy` em todas as respostas do gateway, inclusive nas de erro. |
| Dados enormes | Corpo limitado a 64 KB no gateway e de novo em cada serviço; limites de tamanho em todos os campos. |
| Serviço fora do ar | Prazo por tentativa e até 3 tentativas: a resposta é um 503 claro, nunca uma espera sem fim. |
| SQL injection | Acesso ao banco só pelo SQLAlchemy, com parâmetros. |
| Mensagem estragada na fila | Vai para a fila de mortas (`notificacoes.mortas`) em vez de travar a fila ou derrubar o consumidor. |
| Dependências vulneráveis | Versões fixas por serviço; `pip-audit` de cada serviço no GitHub Actions; Dependabot semanal para Python, Docker e Actions. |
| Contêiner | Serviços, gateway e bancos rodam sem root, com o disco só de leitura, sem capacidades extras e sem novos privilégios. |

## Antes de usar em produção

- Defina `JWT_CHAVE_PRIVADA` (veja o `.env.example`) e guarde-a num cofre de segredos.
- Rode com `DADOS_EXEMPLO=0` (os usuários de exemplo têm senha conhecida) e `DOCS=0`.
- Coloque o gateway atrás de HTTPS.
- Dê a cada PostgreSQL um usuário e uma senha próprios, e troque o usuário padrão do RabbitMQ.
- Com mais de uma cópia do serviço de Usuários, o bloqueio por senha errada precisa de um lugar
  compartilhado (hoje fica na memória de cada cópia; o limite do gateway continua valendo para todas).
- Se um aviso perdido com o RabbitMQ fora do ar for um problema, grave os eventos numa tabela de saída
  (*outbox*) antes de publicar.

## Como relatar um problema

Encontrou uma falha? Não abra uma issue pública: fale diretamente com o autor do repositório.
