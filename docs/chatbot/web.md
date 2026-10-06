# Interface web

A mesma conversa do terminal, numa página: cada passo aparece assim que
termina (propósito, SQL, texto embedado e as primeiras linhas, com CSV para
baixar) e a resposta vem com a conferência dos números e o custo.

## Subir com Docker

Na máquina que vai servir a página, com a stack do SIMCC (`simcc-back`) rodando:

```bash
git clone … && cd simcc-maria
mkdir -p logs              # o container grava os logs aqui (usuário de uid 1000)
cp /caminho/.env .env      # DATABASE_URL, OPENAI_API_KEY, WEB_PASSWORD
GIT_COMMIT=$(git rev-parse --short HEAD) docker compose up -d --build
```

A página fica em `http://localhost:8001` na própria máquina, ou
`http://<ip-da-máquina>:8001` para os outros (`hostname -I` mostra o IP). O
`GIT_COMMIT` não tem nada a ver com o endereço: só vai para o log de auditoria.
Para atualizar: `git pull` e o mesmo `docker compose up -d --build`. Logs do
servidor: `docker compose logs -f`.

O container entra na rede da stack do SIMCC (`simcc_default`, da `simcc-back`)
e fala com o Postgres pelo nome do serviço, `db:5432`. Usuário, senha e banco
continuam vindo do `DATABASE_URL` do `.env`; só o host e a porta são trocados
(`DATABASE_HOST`). Se o banco estiver em outra rede ou outro host, ajuste
`SIMCC_NETWORK` e `DATABASE_HOST` no `.env`.

## `.env`

| Variável | Padrão | Uso |
|---|---|---|
| `WEB_PASSWORD` | — | Senha do login (HTTP Basic). **Sem ela, a página fica aberta a qualquer um que achar o IP**, e cada pergunta é paga com a sua chave da OpenAI |
| `WEB_USER` | `maria` | Usuário do login |
| `WEB_PORT` | 8001 | Porta da página na máquina |
| `DATABASE_HOST` | `db:5432` (só no Docker) | Troca o host:porta do `DATABASE_URL` |
| `SIMCC_NETWORK` | `simcc_default` | Rede Docker onde está o Postgres |
| `WEB_MAX_CONCURRENT` | 3 | Perguntas respondidas ao mesmo tempo; as demais esperam na fila (o pool tem 4 conexões) |
| `WEB_SESSION_IDLE_MIN` | 120 | Sessões paradas há mais tempo são descartadas |

## Sessões e auditoria

Cada navegador recebe um cookie e um `Agent` próprio: o histórico das
perguntas de seguimento, o botão **Limpar** e o log JSONL
(`logs/*_web_*.jsonl`) são por sessão. O `session_start` guarda também o IP e
o navegador. Se o navegador fecha durante uma resposta, o agente é cancelado
(evento `cancelled`) para não gastar tokens à toa. Reiniciar o container
apaga as sessões, mas não os logs.

## Cuidados antes de abrir para outras pessoas

- **HTTPS.** O login HTTP Basic sem HTTPS manda a senha em texto aberto. Com um
  domínio apontando para a máquina, um [Caddy](https://caddyserver.com) na
  frente resolve o certificado sozinho (`seu.dominio { reverse_proxy
  localhost:8001 }`), e a porta 8001 deixa de ser aberta no firewall.
- **Usuário do banco só de leitura e restrito.** O modelo escreve o SQL que
  quiser. A transação é somente leitura, mas qualquer tabela que o
  `DATABASE_URL` enxerga pode ser lida por quem pedir. Um usuário só com
  `SELECT` em `maria` e nas tabelas do `public` que o catálogo descreve
  (mais `INSERT` em `maria.embedding_cache`) limita isso.
