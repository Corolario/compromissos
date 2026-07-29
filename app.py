import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman
from flask_bootstrap import Bootstrap5
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from functools import wraps
from models import db, User, Tarefa, TaskGroup, Note
from forms import (LoginForm, CreateUserForm, TaskForm, EditTaskForm,
                   TaskGroupForm, DeleteForm, ManageMemberForm)
from collections import defaultdict

# Carregar variáveis de ambiente
load_dotenv()

def env_bool(name, default=False):
    """Lê uma variável de ambiente booleana aceitando true/1/yes/on (sem diferenciar caixa)."""
    valor = os.getenv(name)
    if valor is None:
        return default
    return valor.strip().lower() in ('true', '1', 'yes', 'on')


app = Flask(__name__)

# A SECRET_KEY assina os cookies de sessão. Sem ela (ou com um valor
# conhecido) qualquer pessoa consegue forjar uma sessão e se autenticar como
# qualquer usuário. Por isso a aplicação recusa iniciar em vez de usar um
# valor padrão.
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY não definida. Gere uma chave forte e coloque no arquivo .env:\n"
        "  python3 -c 'import secrets; print(secrets.token_hex(32))'"
    )
app.config['SECRET_KEY'] = SECRET_KEY

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///tarefas.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configurações de segurança
app.config['SESSION_COOKIE_SECURE'] = env_bool('SESSION_COOKIE_SECURE')  # True em produção com HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hora
app.config['WTF_CSRF_TIME_LIMIT'] = None  # Token CSRF não expira (usa session)
app.config['WTF_CSRF_SSL_STRICT'] = env_bool('WTF_CSRF_SSL_STRICT')  # True em produção

# Configurações do Bootstrap-Flask
app.config['BOOTSTRAP_SERVE_LOCAL'] = True  # Servir Bootstrap localmente ao invés de CDN

# Confiança em proxies reversos
#
# Atrás de um proxy (nginx), request.remote_addr é o endereço do próprio proxy
# e o IP real do visitante vem no cabeçalho X-Forwarded-For. Sem tratar isso, o
# limite de tentativas de login contaria todo mundo em um balde só.
#
# O padrão é 0 de propósito: confiar no cabeçalho sem proxy na frente permitiria
# a qualquer pessoa forjar X-Forwarded-For e escapar do limite trocando de IP a
# cada tentativa. Defina TRUSTED_PROXY_COUNT=1 apenas quando houver de fato um
# proxy repassando o cabeçalho.
PROXIES_CONFIAVEIS = int(os.getenv('TRUSTED_PROXY_COUNT', '0'))
if PROXIES_CONFIAVEIS > 0:
    app.wsgi_app = ProxyFix(app.wsgi_app,
                            x_for=PROXIES_CONFIAVEIS,
                            x_proto=PROXIES_CONFIAVEIS,
                            x_host=PROXIES_CONFIAVEIS)

# Inicializar extensões
db.init_app(app)
bootstrap = Bootstrap5(app)

# Proteção CSRF
csrf = CSRFProtect(app)

# De onde vem o endereço do visitante
#
# Atrás de Cloudflare Tunnel, nginx ou qualquer proxy, todas as requisições
# chegam do mesmo endereço local e o IP real do visitante vem em um cabeçalho.
# Sem ler esse cabeçalho o limite de tentativas vira um balde único: bastaria
# um atacante errar cinco vezes para trancar a aplicação para todo mundo.
#
# Cloudflare Tunnel : CLIENT_IP_HEADER=CF-Connecting-IP
# nginx             : CLIENT_IP_HEADER=X-Forwarded-For
#
# Só configure quando a aplicação for de fato inalcançável por fora do proxy.
# Se a porta puder ser acessada diretamente, qualquer pessoa forja o cabeçalho
# e escapa do limite trocando de endereço a cada tentativa.
CABECALHO_IP_CLIENTE = os.getenv('CLIENT_IP_HEADER', '').strip()


def identificar_visitante():
    """Endereço usado para contar as tentativas de login de cada visitante."""
    if CABECALHO_IP_CLIENTE:
        valor = request.headers.get(CABECALHO_IP_CLIENTE)
        if valor:
            # X-Forwarded-For chega como uma cadeia "cliente, proxy1, proxy2";
            # o primeiro item é quem originou a requisição.
            return valor.split(',')[0].strip()
    return get_remote_address()


# Limite de tentativas de login
#
# O armazenamento padrão é em memória, que é local a cada processo. Com o
# gunicorn rodando 4 workers, cada um mantém a própria contagem e o limite
# efetivo fica multiplicado pelo número de workers. Continua sendo muito melhor
# que nada, mas para um limite exato configure RATELIMIT_STORAGE_URI apontando
# para um Redis compartilhado.
limiter = Limiter(
    identificar_visitante,
    app=app,
    storage_uri=os.getenv('RATELIMIT_STORAGE_URI', 'memory://'),
    strategy='fixed-window',
)


def login_falhou(resposta):
    """
    Só desconta do limite quando a tentativa falha.

    Um login bem-sucedido responde com redirecionamento; assim quem acerta a
    senha não gasta cota, e quem erra é quem vai sendo contido.
    """
    return resposta.status_code != 302

# Headers de segurança com Flask-Talisman (apenas em produção)
if os.getenv('FLASK_ENV') == 'production':
    # Content Security Policy
    csp = {
        'default-src': "'self'",
        'script-src': "'self' 'unsafe-inline'",  # unsafe-inline necessário para scripts inline nos templates
        'style-src': "'self' 'unsafe-inline'",   # unsafe-inline necessário para estilos inline
        'img-src': "'self' data:",
        'font-src': "'self'",
    }
    Talisman(app,
             content_security_policy=csp,
             force_https=True,
             strict_transport_security=True,
             session_cookie_secure=True)

# Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = None
login_manager.session_protection = 'strong'  # Proteção adicional de sessão

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.errorhandler(429)
def limite_de_tentativas_excedido(erro):
    """Mostra o limite estourado na própria tela de login, com o visual do site."""
    flash(getattr(erro, 'description', None)
          or 'Muitas tentativas. Aguarde alguns minutos e tente novamente.', 'danger')
    return render_template('login.html', form=LoginForm()), 429


@app.before_request
def tornar_sessao_permanente():
    """
    PERMANENT_SESSION_LIFETIME só se aplica a sessões marcadas como
    permanentes. Sem isto o cookie de sessão dura até o navegador fechar e o
    limite de 1 hora configurado nunca entra em vigor.
    """
    session.permanent = True


# ============= DECORADORES =============

def usuarios_visiveis_para(admin):
    """
    IDs dos usuários comuns que um administrador pode ver e gerenciar.

    São os que ele mesmo cadastrou pela interface web e os que já pertencem a
    algum grupo administrado por ele. Sem esse recorte, um administrador
    enxergaria e poderia recrutar os usuários de todos os outros.
    """
    ids = {u.id for u in User.query.filter_by(created_by_id=admin.id, is_admin=False)}
    for grupo in TaskGroup.query.filter_by(admin_id=admin.id):
        ids.update(membro.id for membro in grupo.members)
    return ids


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Você não tem permissão para acessar esta página.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# ============= ROTAS DE AUTENTICAÇÃO =============

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('5 per minute; 40 per hour',
               methods=['POST'],
               deduct_when=login_falhou,
               error_message='Muitas tentativas de login. Aguarde alguns minutos e tente novamente.')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        if user is None:
            # Consome o mesmo tempo de um Argon2 real para que a resposta não
            # revele se o nome de usuário existe (enumeração por timing).
            User.consumir_tempo_de_verificacao()

        if user and user.check_password(form.password.data):
            # Se os parâmetros do Argon2 mudaram desde o cadastro, regrava o
            # hash com os parâmetros atuais aproveitando a senha em claro.
            if user.precisa_rehash():
                user.set_password(form.password.data)
                db.session.commit()
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Usuário ou senha incorretos.', 'danger')

    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logout realizado com sucesso.', 'info')
    return redirect(url_for('login'))


# ============= ROTAS DE TAREFAS =============

@app.route('/')
@login_required
def index():
    # Criar formulário de tarefa
    form = TaskForm()
    form.task_group_id.choices = [('', '--- Selecione um grupo ---')] + [(g.id, g.name) for g in current_user.task_groups]

    # Buscar grupos do usuário
    user_groups = current_user.task_groups

    # Se o usuário não pertence a nenhum grupo, retornar vazio
    if not user_groups:
        return render_template('index.html', tarefas_agrupadas=[], total_tarefas=0, user_groups=user_groups,
                             members_list=[], selected_user_id=None, selected_group_id=None, form=form)

    # Buscar IDs dos grupos do usuário
    group_ids = [group.id for group in user_groups]

    # Obter filtros da query string
    selected_user_id = request.args.get('user_id', type=int)
    selected_group_id = request.args.get('group_id', type=int)

    # Buscar todas as tarefas dos grupos que o usuário pertence
    query = Tarefa.query.filter(Tarefa.task_group_id.in_(group_ids))

    # Aplicar filtro de grupo se selecionado
    if selected_group_id:
        # Verificar se o usuário pertence a este grupo
        if selected_group_id in group_ids:
            query = query.filter(Tarefa.task_group_id == selected_group_id)

    # Aplicar filtro de usuário se selecionado
    if selected_user_id:
        query = query.filter(Tarefa.user_id == selected_user_id)

    tarefas = query.order_by(Tarefa.data).all()

    # Buscar todos os membros dos grupos para o filtro
    members_set = set()
    if selected_group_id:
        # Se um grupo está selecionado, mostrar apenas membros daquele grupo
        selected_group = TaskGroup.query.get(selected_group_id)
        if selected_group:
            for member in selected_group.members.all():
                members_set.add((member.id, member.username))
    else:
        # Mostrar todos os membros de todos os grupos do usuário
        for group in user_groups:
            for member in group.members.all():
                members_set.add((member.id, member.username))
    members_list = sorted(list(members_set), key=lambda x: x[1])  # Ordenar por nome

    # Agrupar tarefas por mês/ano
    tarefas_por_mes = defaultdict(list)
    meses_ordem = []

    # Nomes dos meses em português
    meses_nomes = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }

    for tarefa in tarefas:
        mes_ano = (tarefa.data.year, tarefa.data.month)
        if mes_ano not in tarefas_por_mes:
            meses_ordem.append(mes_ano)
        tarefas_por_mes[mes_ano].append(tarefa)

    # Criar lista formatada de meses com suas tarefas
    tarefas_agrupadas = []
    for ano, mes in meses_ordem:
        mes_nome = f"{meses_nomes[mes]} de {ano}"
        tarefas_agrupadas.append({
            'mes_nome': mes_nome,
            'tarefas': tarefas_por_mes[(ano, mes)]
        })

    return render_template('index.html', tarefas_agrupadas=tarefas_agrupadas, total_tarefas=len(tarefas),
                         user_groups=user_groups, members_list=members_list,
                         selected_user_id=selected_user_id, selected_group_id=selected_group_id, form=form)


@app.route('/adicionar', methods=['POST'])
@login_required
def adicionar():
    form = TaskForm()

    # Preencher choices do SelectField com grupos do usuário
    form.task_group_id.choices = [('', '--- Selecione um grupo ---')] + [(g.id, g.name) for g in current_user.task_groups]

    if form.validate_on_submit():
        # Verificar se o usuário pertence ao grupo
        task_group = TaskGroup.query.get(form.task_group_id.data)
        if not task_group or task_group not in current_user.task_groups:
            flash('Você não pertence a este grupo de tarefas.', 'danger')
            return redirect(url_for('index'))

        tarefa = Tarefa(
            data=form.data.data,
            descricao=form.descricao.data,
            user_id=current_user.id,
            task_group_id=form.task_group_id.data
        )
        db.session.add(tarefa)
        db.session.commit()

        flash('Tarefa adicionada com sucesso!', 'success')
    else:
        # Mostrar erros de validação
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')

    return redirect(url_for('index'))


@app.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    tarefa = Tarefa.query.get_or_404(id)

    # Verificar permissões
    # O administrador do grupo pode editar qualquer tarefa dele
    # Os demais membros só podem editar suas próprias tarefas
    task_group = tarefa.task_group
    if task_group not in current_user.task_groups:
        flash('Você não tem permissão para editar esta tarefa.', 'danger')
        return redirect(url_for('index'))

    if not tarefa.pode_editar(current_user):
        flash('Você não tem permissão para editar esta tarefa.', 'danger')
        return redirect(url_for('index'))

    form = EditTaskForm(obj=tarefa)

    # Preencher choices do SelectField com grupos do usuário
    form.task_group_id.choices = [(g.id, g.name) for g in current_user.task_groups]

    if form.validate_on_submit():
        # Verificar se o usuário pertence ao novo grupo
        new_task_group = TaskGroup.query.get(form.task_group_id.data)
        if not new_task_group or new_task_group not in current_user.task_groups:
            flash('Você não pertence a este grupo de tarefas.', 'danger')
            return redirect(url_for('index'))

        tarefa.data = form.data.data
        tarefa.descricao = form.descricao.data
        tarefa.task_group_id = form.task_group_id.data
        db.session.commit()
        flash('Tarefa atualizada com sucesso!', 'success')
        return redirect(url_for('index'))

    return render_template('editar.html', tarefa=tarefa, form=form)


@app.route('/deletar/<int:id>', methods=['POST'])
@login_required
def deletar(id):
    form = DeleteForm()

    if not form.validate_on_submit():
        flash('Token CSRF inválido.', 'danger')
        return redirect(url_for('index'))

    tarefa = Tarefa.query.get_or_404(id)

    # Verificar permissões
    # O administrador do grupo pode deletar qualquer tarefa dele
    # Os demais membros só podem deletar suas próprias tarefas
    task_group = tarefa.task_group
    if task_group not in current_user.task_groups:
        flash('Você não tem permissão para deletar esta tarefa.', 'danger')
        return redirect(url_for('index'))

    if not tarefa.pode_editar(current_user):
        flash('Você não tem permissão para deletar esta tarefa.', 'danger')
        return redirect(url_for('index'))

    db.session.delete(tarefa)
    db.session.commit()
    flash('Tarefa deletada com sucesso!', 'success')
    return redirect(url_for('index'))


# ============= ROTAS DE ANOTAÇÕES =============

@app.route('/notas')
@login_required
def notas():
    """Página de anotações com gerenciador de arquivos"""
    # Buscar grupos do usuário
    user_groups = current_user.task_groups

    # Se o usuário não pertence a nenhum grupo, retornar vazio
    if not user_groups:
        return render_template('notas.html', notes=[], user_groups=user_groups,
                             selected_group_id=None, selected_note_id=None,
                             current_note=None, members_list=[])

    # Buscar IDs dos grupos do usuário
    group_ids = [group.id for group in user_groups]

    # Obter filtros da query string
    selected_group_id = request.args.get('group_id', type=int)
    selected_note_id = request.args.get('note_id', type=int)
    selected_user_id = request.args.get('user_id', type=int)

    # Buscar todas as notas dos grupos que o usuário pertence
    query = Note.query.filter(Note.task_group_id.in_(group_ids))

    # Aplicar filtro de grupo se selecionado
    if selected_group_id and selected_group_id in group_ids:
        query = query.filter(Note.task_group_id == selected_group_id)

    # Aplicar filtro de usuário se selecionado
    if selected_user_id:
        query = query.filter(Note.user_id == selected_user_id)

    notes = query.order_by(Note.updated_at.desc()).all()

    # Buscar todos os membros dos grupos para o filtro
    members_set = set()
    if selected_group_id:
        # Se um grupo está selecionado, mostrar apenas membros daquele grupo
        selected_group = TaskGroup.query.get(selected_group_id)
        if selected_group:
            for member in selected_group.members.all():
                members_set.add((member.id, member.username))
    else:
        # Mostrar todos os membros de todos os grupos do usuário
        for group in user_groups:
            for member in group.members.all():
                members_set.add((member.id, member.username))
    members_list = sorted(list(members_set), key=lambda x: x[1])  # Ordenar por nome

    # Buscar nota selecionada
    current_note = None
    if selected_note_id:
        current_note = Note.query.get(selected_note_id)
        # Verificar se o usuário tem acesso à nota
        if current_note and current_note.task_group_id not in group_ids:
            current_note = None

    return render_template('notas.html', notes=notes, user_groups=user_groups,
                         selected_group_id=selected_group_id,
                         selected_note_id=selected_note_id,
                         selected_user_id=selected_user_id,
                         current_note=current_note, members_list=members_list)


@app.route('/notas/criar', methods=['POST'])
@login_required
def criar_nota():
    """Criar nova nota"""
    title = request.form.get('title', '').strip()
    task_group_id = request.form.get('task_group_id', type=int)

    if not title:
        flash('O título da nota não pode estar vazio.', 'danger')
        return redirect(url_for('notas'))

    if not task_group_id:
        flash('Você deve selecionar um grupo.', 'danger')
        return redirect(url_for('notas'))

    # Verificar se o usuário pertence ao grupo
    task_group = TaskGroup.query.get(task_group_id)
    if not task_group or task_group not in current_user.task_groups:
        flash('Você não pertence a este grupo de tarefas.', 'danger')
        return redirect(url_for('notas'))

    note = Note(
        title=title,
        content='',
        user_id=current_user.id,
        task_group_id=task_group_id
    )
    db.session.add(note)
    db.session.commit()

    flash('Nota criada com sucesso!', 'success')
    return redirect(url_for('notas', note_id=note.id, group_id=task_group_id))


@app.route('/notas/<int:id>/atualizar', methods=['POST'])
@login_required
def atualizar_nota(id):
    """Atualizar conteúdo da nota - apenas o autor ou o administrador do grupo"""
    note = Note.query.get_or_404(id)

    # Verificar se pertence ao grupo
    if note.task_group not in current_user.task_groups:
        return {'success': False, 'message': 'Você não tem permissão para editar esta nota.'}, 403

    # Verificar se é o autor ou o administrador do grupo
    if not note.pode_editar(current_user):
        return {'success': False,
                'message': 'Apenas o autor ou o administrador do grupo podem editar esta nota.'}, 403

    # Quem pode editar também pode mover a nota para outro dos seus grupos
    task_group_id = request.form.get('task_group_id', type=int)
    if task_group_id:
        # Verificar se o usuário pertence ao novo grupo
        new_group = TaskGroup.query.get(task_group_id)
        if new_group and new_group in current_user.task_groups:
            note.task_group_id = task_group_id

    content = request.form.get('content', '')
    title = request.form.get('title', '').strip()

    if title:
        note.title = title
    note.content = content
    db.session.commit()

    return {
        'success': True,
        'message': 'Nota atualizada com sucesso!',
        'group_name': note.task_group.name
    }


@app.route('/notas/<int:id>/deletar', methods=['POST'])
@login_required
def deletar_nota(id):
    """Deletar nota - o autor ou o administrador do grupo podem deletar"""
    note = Note.query.get_or_404(id)

    task_group = note.task_group
    if task_group not in current_user.task_groups:
        flash('Você não tem permissão para deletar esta nota.', 'danger')
        return redirect(url_for('notas'))

    # Verificar permissões - o autor ou o administrador do grupo podem deletar
    if not note.pode_editar(current_user):
        flash('Apenas o criador da nota ou o administrador do grupo podem deletá-la.', 'danger')
        return redirect(url_for('notas'))

    group_id = note.task_group_id
    db.session.delete(note)
    db.session.commit()
    flash('Nota deletada com sucesso!', 'success')
    return redirect(url_for('notas', group_id=group_id))


# ============= ROTAS DE ADMINISTRAÇÃO =============

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    """Dashboard de administração"""
    groups = TaskGroup.query.filter_by(admin_id=current_user.id).all()

    # Mostra apenas os usuários comuns que já são membros de algum grupo deste
    # administrador, mais os que ele mesmo cadastrou. Listar todos os usuários
    # do sistema expunha os usuários de outros administradores.
    users = (User.query
             .filter_by(is_admin=False)
             .filter(User.id.in_(usuarios_visiveis_para(current_user)))
             .all())

    # Em quais grupos deste administrador cada usuário está. Um usuário pode
    # pertencer a vários grupos ao mesmo tempo; sem isto no painel não havia
    # como saber a quais.
    grupos_por_usuario = defaultdict(list)
    for grupo in groups:
        for membro in grupo.members:
            grupos_por_usuario[membro.id].append(grupo.name)

    return render_template('admin/dashboard.html', groups=groups, users=users,
                           grupos_por_usuario=grupos_por_usuario)


@app.route('/admin/groups/create', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_create_group():
    """Criar novo grupo de tarefas"""
    form = TaskGroupForm()

    if form.validate_on_submit():
        group = TaskGroup(
            name=form.name.data,
            description=form.description.data,
            admin_id=current_user.id
        )
        db.session.add(group)
        db.session.commit()
        flash(f'Grupo "{form.name.data}" criado com sucesso!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/create_group.html', form=form)


@app.route('/admin/groups/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_group(id):
    """Editar grupo de tarefas"""
    group = TaskGroup.query.get_or_404(id)

    # Verificar se o grupo pertence ao admin
    if group.admin_id != current_user.id:
        flash('Você não tem permissão para editar este grupo.', 'danger')
        return redirect(url_for('admin_dashboard'))

    form = TaskGroupForm(obj=group)

    if form.validate_on_submit():
        group.name = form.name.data
        group.description = form.description.data
        db.session.commit()
        flash(f'Grupo "{form.name.data}" atualizado com sucesso!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/edit_group.html', group=group, form=form)


@app.route('/admin/groups/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_group(id):
    """Deletar grupo de tarefas"""
    form = DeleteForm()

    if not form.validate_on_submit():
        flash('Token CSRF inválido.', 'danger')
        return redirect(url_for('admin_dashboard'))

    group = TaskGroup.query.get_or_404(id)

    # Verificar se o grupo pertence ao admin
    if group.admin_id != current_user.id:
        flash('Você não tem permissão para deletar este grupo.', 'danger')
        return redirect(url_for('admin_dashboard'))

    group_name = group.name
    db.session.delete(group)
    db.session.commit()
    flash(f'Grupo "{group_name}" deletado com sucesso!', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/groups/<int:id>/members', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_group_members(id):
    """Gerenciar membros do grupo"""
    group = TaskGroup.query.get_or_404(id)

    # Verificar se o grupo pertence ao admin
    if group.admin_id != current_user.id:
        flash('Você não tem permissão para gerenciar este grupo.', 'danger')
        return redirect(url_for('admin_dashboard'))

    form = ManageMemberForm()

    # Listar membros atuais e usuários disponíveis. O administrador só pode
    # recrutar entre os usuários que ele gerencia; ele próprio sempre aparece,
    # já que precisa ser membro do grupo para enxergar o conteúdo.
    current_members = group.members.all()
    ids_recrutaveis = usuarios_visiveis_para(current_user) | {current_user.id}
    all_users = User.query.filter(User.id.in_(ids_recrutaveis)).all()

    if request.method == 'POST':
        # Preencher choices dinamicamente antes da validação
        action = request.form.get('action')
        if action == 'add':
            available_users = [u for u in all_users if u not in current_members]
            form.user_id.choices = [(u.id, u.username) for u in available_users]
        else:  # remove
            form.user_id.choices = [(u.id, u.username) for u in current_members]

        if form.validate_on_submit():
            user = User.query.get(form.user_id.data)
            if not user:
                flash('Usuário não encontrado.', 'danger')
                return redirect(url_for('admin_group_members', id=id))

            if form.action.data == 'add':
                if user not in current_members:
                    group.members.append(user)
                    db.session.commit()
                    flash(f'Usuário "{user.username}" adicionado ao grupo.', 'success')
                else:
                    flash(f'Usuário "{user.username}" já está no grupo.', 'info')
            elif form.action.data == 'remove':
                if user in current_members:
                    group.members.remove(user)
                    db.session.commit()
                    flash(f'Usuário "{user.username}" removido do grupo.', 'success')
                else:
                    flash(f'Usuário "{user.username}" não está no grupo.', 'info')

            return redirect(url_for('admin_group_members', id=id))

    # Para GET, preparar choices para ambos os formulários
    available_users = [u for u in all_users if u not in current_members]

    return render_template('admin/group_members.html', group=group,
                         current_members=current_members,
                         available_users=available_users, form=form)


@app.route('/admin/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_create_user():
    """Criar novo usuário comum"""
    form = CreateUserForm()

    if form.validate_on_submit():
        user = User(username=form.username.data, is_admin=False,
                    created_by_id=current_user.id)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash(f'Usuário "{form.username.data}" criado com sucesso!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/create_user.html', form=form)


# ============= INICIALIZAÇÃO =============

def init_db():
    """Cria as tabelas do banco de dados"""
    with app.app_context():
        db.create_all()
        print("Banco de dados inicializado!")


if __name__ == '__main__':
    init_db()
    # O debugger do Werkzeug executa código arbitrário através do navegador,
    # portanto só é habilitado fora de produção. O bind padrão é 127.0.0.1
    # para não expor o servidor de desenvolvimento na rede; use
    # FLASK_RUN_HOST=0.0.0.0 se precisar acessar de outra máquina.
    modo_debug = os.getenv('FLASK_ENV', 'development') != 'production'
    app.run(host=os.getenv('FLASK_RUN_HOST', '127.0.0.1'), port=5000, debug=modo_debug)
