# Segurança

## Relatar uma vulnerabilidade

Encontrou uma falha? Abra uma
[issue](https://github.com/Corolario/agenda-tarefas/issues) descrevendo o
problema e como reproduzi-lo. Se a falha permitir acesso a dados de outras
pessoas, evite publicar os detalhes de exploração até que haja correção.

---

## Proteções implementadas

### Senhas

Guardadas como hash **Argon2id**, através da biblioteca `argon2-cffi`. O Argon2
venceu a Password Hashing Competition e é o padrão recomendado hoje: consome
memória de propósito, o que torna ataques com GPU muito mais caros do que
contra algoritmos apenas baseados em iteração.

A senha em texto nunca é gravada nem registrada em log. Quando os parâmetros do
Argon2 mudam, o hash é regravado automaticamente no login seguinte.

### Tentativas de login

Limitadas por endereço de origem: **3 por minuto, 10 por hora e 25 por dia**,
ajustável em `LOGIN_RATE_LIMIT`.

Só tentativas **erradas** descontam do limite. Quem acerta a senha nunca é
bloqueado, mesmo entrando várias vezes seguidas.

Atrás de um proxy, é indispensável configurar `CLIENT_IP_HEADER` para que o
limite enxergue o visitante real. Sem isso todas as tentativas são contadas
como se viessem da mesma pessoa, e um desconhecido consegue trancar o login de
todos. Veja [docs/deploy.md](docs/deploy.md).

### Descoberta de nomes de usuário

Um login com usuário inexistente leva o mesmo tempo de um com usuário válido e
senha errada. Sem esse cuidado, a diferença de tempo de resposta permitiria
descobrir quais nomes existem — e a mensagem de erro é sempre a mesma, sem
distinguir os dois casos.

### Sessão

| Proteção | Efeito |
|---|---|
| `HttpOnly` | JavaScript não lê o cookie de sessão |
| `SameSite=Lax` | Reduz o alcance de requisições vindas de outros sites |
| `Secure` | Em produção, o cookie só trafega por HTTPS |
| Expiração em 1 hora | A sessão vence sozinha |
| `session_protection = 'strong'` | Invalida a sessão se as características da conexão mudarem |

A `SECRET_KEY` assina esses cookies. **A aplicação recusa iniciar sem ela**:
com uma chave previsível, qualquer pessoa monta um cookie válido e entra como
administrador.

### Formulários

Todos passam por Flask-WTF, com **proteção CSRF** aplicada a todas as
requisições que alteram dados — inclusive a gravação automática das anotações,
feita por JavaScript.

Os tamanhos são validados no servidor, não apenas no navegador:

| Campo | Limite |
|---|---|
| Nome de usuário | 3 a 80 caracteres |
| Senha | mínimo 6 caracteres |
| Nome do grupo | 3 a 120 caracteres |
| Descrição do grupo | até 500 caracteres |
| Descrição do compromisso | 1 a 1.000 caracteres |
| Título da anotação | até 200 caracteres |
| Texto da anotação | até 50.000 caracteres |

Os limites das anotações evitam que uma única requisição grave megabytes no
banco.

### Cabeçalhos HTTP

Com `FLASK_ENV=production`, o Flask-Talisman aplica:

- **HTTPS obrigatório** — acessos por HTTP são redirecionados
- **HSTS** — o navegador passa a exigir HTTPS por conta própria
- **Content Security Policy** — restringe de onde scripts, estilos, imagens e
  fontes podem vir
- **X-Frame-Options** — impede que a aplicação seja embutida em outro site
- **X-Content-Type-Options** — impede adivinhação de tipo de conteúdo

O Bootstrap é servido pela própria aplicação, sem CDN externa.

### Permissões

Alterar um compromisso ou anotação exige ser o autor **ou** o administrador
daquele grupo. A marca de administrador do sistema, por si só, não dá acesso ao
conteúdo de ninguém — ela apenas abre a área de administração.

Cada administrador enxerga somente os próprios grupos e usuários. Detalhes em
[docs/administracao.md](docs/administracao.md).

### Injeção de SQL e XSS

As consultas passam pelo SQLAlchemy com parâmetros vinculados, sem concatenação
de texto. Os templates Jinja escapam a saída automaticamente, e nenhum ponto da
aplicação desativa esse escape — inclusive nas anotações, que são texto livre.

---

## Configuração recomendada

```env
SECRET_KEY=<gere com secrets.token_hex(32)>
FLASK_ENV=production
SESSION_COOKIE_SECURE=True
WTF_CSRF_SSL_STRICT=True
CLIENT_IP_HEADER=CF-Connecting-IP   # ou X-Forwarded-For com nginx
```

### Lista de conferência

- [x] Senhas com Argon2id
- [x] Proteção CSRF em todos os formulários
- [x] Limite de tentativas de login
- [x] Cabeçalhos de segurança HTTP
- [x] Cookies com HttpOnly, SameSite e Secure
- [x] Sessão com expiração
- [x] Validação de tamanho no servidor
- [x] Dependências com versões fixadas
- [ ] HTTPS na frente da aplicação — **necessário**, veja [docs/deploy.md](docs/deploy.md)
- [ ] `CLIENT_IP_HEADER` configurado, se houver proxy
- [ ] Firewall permitindo apenas o necessário
- [ ] Backup periódico do banco
- [ ] Dependências revisadas de tempos em tempos

---

## Cuidados na operação

**Nunca versione o `.env`.** Ele está no `.gitignore`; mantenha assim.

**Só configure `CLIENT_IP_HEADER` se a aplicação for inalcançável por fora do
proxy.** Se a porta também estiver aberta na internet, o cabeçalho pode ser
forjado para escapar do limite de tentativas.

**Faça backup antes de atualizar.** O procedimento está em
[docs/deploy.md](docs/deploy.md).

**Revise as dependências periodicamente:**

```bash
pip list --outdated
```

---

## Limitações conhecidas

**Sem recuperação de senha.** Quem perde a senha ou estoura o limite de
tentativas depende de um administrador com acesso ao servidor
(`create_user.py`, opção 3).

**Contador de tentativas por processo.** Com o padrão `memory://`, cada worker
do gunicorn mantém a própria contagem, então o limite efetivo é multiplicado
pelo número de workers. Para um limite exato, use um Redis compartilhado em
`RATELIMIT_STORAGE_URI`.

**Sem registro de auditoria.** A aplicação não guarda histórico de quem alterou
ou apagou o quê.

**Banco SQLite.** É o único banco configurado e testado. Usar PostgreSQL exige
acrescentar um driver (`psycopg`) ao `requirements.txt`, que não vem incluído.
