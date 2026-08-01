# Publicar em um servidor

A aplicação roda em um contêiner Docker e guarda os dados em um arquivo SQLite
dentro de `data/`. Não depende de banco externo, Redis nem fila.

---

## Antes de começar

No servidor você precisa de **Docker** com o plugin **Compose**:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
docker --version && docker compose version
```

---

## Subir a aplicação

### 1. Obter o código

```bash
git clone https://github.com/Corolario/agenda-tarefas.git
cd agenda-tarefas
```

### 2. Criar o arquivo de configuração

```bash
cp .env.example .env
```

Gere uma chave secreta e coloque no `.env`:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

**A `SECRET_KEY` é obrigatória.** Ela assina os cookies de sessão: sem uma
chave forte e privada, qualquer pessoa consegue montar um cookie válido e
entrar como administrador. O `docker compose` recusa subir se ela estiver
faltando — é proposital, não é falha.

Confira também o **fuso horário**, já que os horários são gravados e exibidos
nele:

```env
TZ=America/Sao_Paulo
```

### 3. Preparar a pasta de dados

```bash
mkdir -p data
```

Crie **antes** de subir o contêiner. Se o Docker criar a pasta sozinho, ela
nasce pertencendo ao `root` e o contêiner entra em ciclo de reinício. Confira
também se `UID` e `GID` no `.env` são os seus:

```bash
id -u    # UID
id -g    # GID
```

### 4. Subir

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f
```

A aplicação responde na porta **5000**.

### 5. Criar o primeiro administrador

Não existe cadastro pela tela de login: o primeiro administrador é criado pela
linha de comando, dentro do contêiner.

```bash
docker compose exec web python create_user.py
```

Escolha a opção **1** e informe nome e senha (mínimo 6 caracteres). Depois
entre na aplicação, crie um grupo, crie os usuários e adicione todos ao grupo —
incluindo você. O passo a passo está em [administracao.md](administracao.md).

---

## Expor na internet

A aplicação assume que há **HTTPS** na frente dela. O `.env.example` já vem com
`FLASK_ENV=production`, e nesse modo o Flask-Talisman redireciona qualquer
acesso HTTP para HTTPS. Publicar a porta 5000 direto na internet, sem TLS, não
funciona — o navegador entra em ciclo de redirecionamento.

Escolha um dos dois caminhos abaixo.

### Opção A — Cloudflare Tunnel (sem IP público)

Funciona mesmo com o servidor atrás de NAT, sem abrir porta nenhuma. O
`cloudflared` faz uma conexão de saída até a Cloudflare, que passa a entregar
o tráfego por ela.

Aponte o túnel para `http://localhost:5000` e, no `.env`, defina:

```env
CLIENT_IP_HEADER=CF-Connecting-IP
TRUSTED_PROXY_COUNT=0
```

**A primeira linha é essencial.** Com o túnel, todas as requisições chegam à
aplicação vindas do próprio `cloudflared`, com o mesmo endereço. Sem dizer onde
está o IP verdadeiro, o limite de tentativas de login trata todo mundo como um
visitante só: **cinco senhas erradas de um desconhecido qualquer trancariam o
login de toda a equipe**. O cabeçalho `CF-Connecting-IP` é preenchido pela
Cloudflare e traz o endereço real de cada visitante.

Isso é seguro aqui porque a aplicação só é alcançável através do túnel. Se a
porta 5000 também estivesse aberta para a internet, qualquer pessoa poderia
forjar esse cabeçalho e escapar do limite trocando de endereço a cada
tentativa.

O `TRUSTED_PROXY_COUNT` pode ficar em `0`: o `cloudflared` já envia o cabeçalho
`X-Forwarded-Proto`, que é o que o Flask-Talisman consulta para saber que a
conexão original era HTTPS.

### Opção B — nginx com Let's Encrypt

```bash
sudo apt install nginx certbot python3-certbot-nginx -y
sudo nano /etc/nginx/sites-available/agenda
```

```nginx
server {
    listen 80;
    server_name seu-dominio.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/agenda /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
sudo certbot --nginx -d seu-dominio.com
```

No `.env`:

```env
CLIENT_IP_HEADER=X-Forwarded-For
TRUSTED_PROXY_COUNT=1
```

Com nginx, feche a porta 5000 no firewall para que ninguém alcance a aplicação
por fora do proxy:

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## Variáveis de ambiente

O `.env` é a **única fonte de configuração**: o `docker-compose.yml` o lê por
inteiro e repassa ao contêiner, sem repetir valor nenhum. Para mudar qualquer
comportamento, edite o `.env` e reinicie — o compose não precisa ser tocado.

Se o arquivo não existir, o `docker compose` recusa subir. Comece sempre
copiando o modelo, que já vem preenchido para produção:

```bash
cp .env.example .env
```

A única exceção é o `DATABASE_URL`, que **não fica no `.env`**: ele descreve a
estrutura da imagem, não uma escolha de quem instala. O `docker-compose.yml` o
fixa em `/app/data/tarefas.db`, a pasta persistida em volume.

O caminho precisa ser absoluto. Um caminho relativo, como
`sqlite:///tarefas.db`, seria resolvido pelo Flask-SQLAlchemy dentro de
`instance/` — ou seja, `/app/instance/tarefas.db`, **fora do volume**. A
aplicação funcionaria normalmente até o primeiro `docker compose down` seguido
de recriação, quando os dados desapareceriam sem aviso.

### Obrigatória

| Variável | Descrição |
|---|---|
| `SECRET_KEY` | Assina os cookies de sessão. Gere com `secrets.token_hex(32)` e mantenha em segredo. **Vem vazia no modelo**, e a aplicação recusa iniciar enquanto assim estiver. |

### Identificação do visitante

| Variável | Padrão | Descrição |
|---|---|---|
| `CLIENT_IP_HEADER` | *(vazio)* | Cabeçalho que traz o IP real. `CF-Connecting-IP` com Cloudflare Tunnel, `X-Forwarded-For` com nginx. Vazio quando a aplicação é acessada direto. |
| `TRUSTED_PROXY_COUNT` | `0` | Quantos proxies existem na frente. Afeta o esquema e o host que a aplicação enxerga. |

Preencha `CLIENT_IP_HEADER` **apenas** se a aplicação for inalcançável por fora
do proxy. Caso contrário, o cabeçalho pode ser forjado.

### Comportamento

Os valores abaixo são os que vêm no `.env.example`.

| Variável | No modelo | Descrição |
|---|---|---|
| `TZ` | `America/Sao_Paulo` | Fuso horário. Os horários são gravados e exibidos nele, sem conversão. |
| `FLASK_ENV` | `production` | Ativa HTTPS obrigatório, HSTS e CSP. Use `development` para trabalhar em `http://localhost`. |
| `GUNICORN_WORKERS` | `2` | Processos do servidor. Manter baixo por causa do SQLite. |
| `LOGIN_RATE_LIMIT` | `3 per minute; 10 per hour; 25 per day` | Tentativas de login **mal-sucedidas** por endereço. |
| `RATELIMIT_STORAGE_URI` | `memory://` | Onde fica o contador de tentativas. |
| `SESSION_COOKIE_SECURE` | `True` | Envia o cookie de sessão apenas por HTTPS. |
| `WTF_CSRF_SSL_STRICT` | `True` | Confere a origem das requisições sob HTTPS. |
| `UID` / `GID` | `1000` | Dono dos arquivos em `data/`, para não ficarem como `root`. |

> Ao rodar **fora** do contêiner, com `python app.py`, troque `FLASK_ENV` para
> `development` e `SESSION_COOKIE_SECURE`/`WTF_CSRF_SSL_STRICT` para `False`.
> Com os valores de produção, o navegador é redirecionado para HTTPS e o cookie
> de sessão não é enviado, impedindo o login em `http://localhost`.

### Sobre o limite de login

Só tentativas **erradas** descontam. Quem acerta a senha nunca esbarra no
limite, mesmo entrando várias vezes seguidas.

O bloqueio é **temporário e se desfaz sozinho** — ninguém precisa ser
destravado manualmente. Cada janela conta a partir da primeira tentativa dela,
então a espera depende de qual limite foi atingido:

| Limite atingido | Espera até |
|---|---|
| 3 por minuto | 1 minuto |
| 10 por hora | 1 hora |
| 25 por dia | 24 horas |

Passado esse tempo, a senha correta volta a funcionar normalmente. Se achar
apertado para o seu uso, ajuste `LOGIN_RATE_LIMIT`.

O administrador só é necessário em outra situação: quando a pessoa **esqueceu**
a senha. A aplicação não tem recuperação por conta própria, então nesse caso
alguém precisa redefini-la com o `create_user.py` (opção 3).

Com mais de um worker, o contador em memória é mantido **por processo**, então o
limite efetivo fica multiplicado pelo número de workers. Para um limite exato,
aponte `RATELIMIT_STORAGE_URI` para um Redis compartilhado.

---

## Operação

```bash
docker compose logs -f          # acompanhar
docker compose restart          # reiniciar
docker compose stop             # parar
docker compose down             # parar e remover
docker stats                    # uso de recursos
```

O contêiner sobe com `restart: unless-stopped` e volta sozinho após um reboot.

### Atualizar

```bash
cp data/tarefas.db data/backup-$(date +%Y%m%d).db
git pull
docker compose up -d --build
docker compose logs -f
```

### Backup

O banco fica em `data/`. Como a aplicação usa modo WAL, existem arquivos
auxiliares `-wal` e `-shm` ao lado dele; copiar os três garante um retrato
consistente:

```bash
tar -czf backup-$(date +%Y%m%d).tar.gz data/
```

Para uma cópia com a aplicação em uso, prefira o comando do próprio SQLite, que
resolve o WAL:

```bash
docker compose exec web python -c "
import sqlite3
o = sqlite3.connect('/app/data/tarefas.db')
d = sqlite3.connect('/app/data/backup.db')
o.backup(d); d.close(); o.close()
print('backup em data/backup.db')"
```

---

## Problemas comuns

### O contêiner reinicia sem parar

Quase sempre é permissão em `data/`, criada como `root` pelo Docker.

```bash
docker compose down
sudo rm -rf data/
mkdir -p data
echo "UID=$(id -u)" >> .env
echo "GID=$(id -g)" >> .env
docker compose up -d --build
```

### `SECRET_KEY` não definida

O `docker compose` recusa subir e mostra a mensagem. Gere a chave e coloque no
`.env`:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

### O navegador fica em ciclo de redirecionamento

Em produção a aplicação exige HTTPS. Acontece ao tentar acessar a porta 5000
direto por HTTP. Coloque a aplicação atrás do Cloudflare Tunnel ou do nginx com
certificado, ou, apenas para testar, use `FLASK_ENV=development` no `.env`.

### Um usuário trancou o login de todos

Falta configurar `CLIENT_IP_HEADER`. Sem ele, atrás de um proxy, todas as
tentativas são contadas como se fossem do mesmo visitante. Veja a seção
[Expor na internet](#expor-na-internet).

### Horários com diferença de algumas horas

Confira o `TZ` no `.env`. Registros gravados antes da mudança permanecem no
fuso antigo: a coluna não guarda essa informação, então não há conversão
retroativa.

### O contêiner aparece como `unhealthy`

O healthcheck consulta `http://localhost:5000/login` de dentro do contêiner.
Veja o que os logs dizem:

```bash
docker compose logs --tail=50 web
```

### Esqueci a senha do administrador

```bash
docker compose exec web python create_user.py
```

Opção **3**, escolha o usuário e defina a nova senha.
