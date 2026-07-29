# Gerenciador de Compromissos

Aplicação web para equipes pequenas organizarem compromissos e anotações em
grupos compartilhados. Cada grupo tem um administrador responsável, e os
membros enxergam o que os colegas estão fazendo sem poder alterar o que não é
deles.

Feita em Flask com banco SQLite, roda inteira em um contêiner Docker.

---

## Funcionalidades

### Compromissos

- Cada compromisso tem data, descrição, autor e grupo
- A listagem agrupa por mês e mostra quem criou cada item
- Filtros por grupo e por membro
- Cada pessoa edita e apaga os próprios compromissos; o administrador do grupo
  pode editar e apagar os de qualquer membro daquele grupo

### Anotações

- Editor de texto livre, uma aba própria ao lado dos compromissos
- **Gravação automática**: o texto é salvo cerca de 1,5 segundo depois que você
  para de digitar, sem precisar clicar em nada
- Anotações de outras pessoas aparecem em modo somente leitura
- É possível mover uma anotação para outro grupo seu
- Mesma regra de edição dos compromissos: autor ou administrador do grupo

### Grupos e usuários

- Um usuário pode participar de **vários grupos** ao mesmo tempo
- O administrador cria grupos, cria usuários e define quem entra em cada grupo
- Cada administrador enxerga e gerencia apenas os próprios grupos e usuários

---

## Como funcionam as permissões

Existem dois papéis, e a diferença entre eles costuma gerar confusão:

| Papel | O que define | O que permite |
|---|---|---|
| **Administrador do sistema** | Campo `is_admin`, ligado só pelo `create_user.py` | Entrar na área de administração para criar grupos e usuários |
| **Administrador do grupo** | Quem criou aquele grupo | Editar e apagar todo o conteúdo **daquele** grupo |

O ponto importante: **poder sobre conteúdo vem de ser dono do grupo, não da
flag de administrador**. Um administrador do sistema que seja apenas membro de
um grupo alheio se comporta ali como qualquer outro membro — vê tudo, mas só
mexe no que é dele.

Detalhes completos em [docs/administracao.md](docs/administracao.md).

---

## Tecnologias

| Componente | Para quê |
|---|---|
| **Flask** + **Jinja2** | Framework web e templates |
| **Flask-SQLAlchemy** | ORM sobre o banco SQLite |
| **Flask-Login** | Sessão e autenticação |
| **argon2-cffi** | Hash das senhas (Argon2id) |
| **Flask-WTF** | Proteção CSRF e validação de formulários |
| **Flask-Talisman** | Cabeçalhos de segurança HTTP em produção |
| **Flask-Limiter** | Limite de tentativas de login |
| **Bootstrap-Flask** | Bootstrap 5 servido localmente, sem CDN |
| **Gunicorn** | Servidor de produção |
| **Docker** | Empacotamento e execução |

Versões exatas, incluindo as transitivas, estão fixadas em `requirements.txt`.

---

## Início rápido (desenvolvimento local)

Requer **Python 3.10 ou superior** (o contêiner usa 3.13).

```bash
# 1. Dependências
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configuração
cp .env.example .env
```

Abra o `.env` e defina uma `SECRET_KEY`. **A aplicação recusa iniciar sem
ela** — é a chave que assina os cookies de sessão, e um valor previsível
permitiria a qualquer pessoa forjar uma sessão de administrador.

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

```bash
# 3. Iniciar (as tabelas são criadas automaticamente)
python app.py

# 4. Em outro terminal, criar o primeiro administrador
python create_user.py     # escolha a opção 1
```

Acesse **http://localhost:5000** e entre com o administrador criado.

> Por segurança o servidor de desenvolvimento escuta apenas em `localhost`.
> Para acessar de outra máquina na rede, use `FLASK_RUN_HOST=0.0.0.0`.

### Primeiros passos na interface

1. Entre com o administrador
2. Clique em **Administração** no topo
3. Crie um **grupo** (o nome precisa ter ao menos 3 caracteres)
4. Crie os **usuários** da equipe
5. Em **Gerenciar Membros**, adicione os usuários ao grupo — e **adicione-se
   também**: só quem é membro enxerga o conteúdo
6. Volte para a página principal e crie o primeiro compromisso

---

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/deploy.md](docs/deploy.md) | Publicar em um VPS: Docker, Cloudflare Tunnel, nginx, variáveis de ambiente, backup e problemas comuns |
| [docs/administracao.md](docs/administracao.md) | Gerenciar usuários e grupos, o script `create_user.py`, e o modelo de permissões em detalhe |
| [SECURITY.md](SECURITY.md) | Proteções implementadas e como relatar uma vulnerabilidade |

---

## Estrutura do projeto

```
agenda-tarefas/
├── app.py                    # Aplicação Flask: rotas e configuração
├── models.py                 # Modelos (User, TaskGroup, Tarefa, Note)
├── forms.py                  # Formulários e regras de validação
├── create_user.py            # Gerenciamento de usuários pela linha de comando
├── init_db.py                # Criação das tabelas (usado na subida do contêiner)
├── templates/
│   ├── base.html             # Layout, cabeçalho e abas
│   ├── login.html
│   ├── index.html            # Compromissos
│   ├── notas.html            # Anotações
│   ├── editar.html           # Edição de compromisso
│   └── admin/                # Painel de administração
│       ├── dashboard.html
│       ├── create_group.html
│       ├── edit_group.html
│       ├── group_members.html
│       └── create_user.html
├── docs/                     # Documentação detalhada
├── instance/                 # Banco SQLite ao rodar localmente
├── data/                     # Banco SQLite ao rodar em contêiner
├── requirements.txt          # Dependências com versões fixadas
├── Dockerfile
├── docker-compose.yml
└── .env.example              # Modelo de configuração
```

> As duas pastas do banco não são redundância. Rodando local, o
> `DATABASE_URL` padrão usa um caminho relativo, e o Flask-SQLAlchemy o resolve
> dentro de `instance/`. No contêiner, o `docker-compose.yml` fixa o caminho
> absoluto `/app/data/tarefas.db`, que é a pasta persistida em volume. Ambas são
> criadas sozinhas no primeiro uso.

---

## Limites de tamanho

Valores recusados pelos formulários, com mensagem na própria tela:

| Campo | Limite |
|---|---|
| Nome de usuário | 3 a 80 caracteres |
| Senha | mínimo 6 caracteres |
| Nome do grupo | 3 a 120 caracteres |
| Descrição do grupo | até 500 caracteres |
| Descrição do compromisso | 1 a 1.000 caracteres |
| Título da anotação | até 200 caracteres |
| Texto da anotação | até 50.000 caracteres |

---

## Rotas

| Rota | Método | Função |
|---|---|---|
| `/login` | GET, POST | Entrada no sistema |
| `/logout` | GET | Encerrar sessão |
| `/` | GET | Compromissos, com filtros |
| `/adicionar` | POST | Criar compromisso |
| `/editar/<id>` | GET, POST | Editar compromisso |
| `/deletar/<id>` | POST | Apagar compromisso |
| `/notas` | GET | Anotações |
| `/notas/criar` | POST | Criar anotação |
| `/notas/<id>/atualizar` | POST | Gravação automática |
| `/notas/<id>/deletar` | POST | Apagar anotação |
| `/admin` | GET | Painel de administração |
| `/admin/groups/create` | GET, POST | Criar grupo |
| `/admin/groups/<id>/edit` | GET, POST | Editar grupo |
| `/admin/groups/<id>/delete` | POST | Apagar grupo |
| `/admin/groups/<id>/members` | GET, POST | Gerenciar membros |
| `/admin/users/create` | GET, POST | Criar usuário |

Todas exigem sessão iniciada, exceto `/login`. As rotas sob `/admin` exigem
`is_admin`.
