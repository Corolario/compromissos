from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from datetime import datetime

db = SQLAlchemy()

# Inicializar Argon2 Password Hasher
# Argon2id é a variante recomendada que combina resistência a ataques de tempo e memória
ph = PasswordHasher()

# Hash descartável usado para gastar o mesmo tempo de CPU de uma verificação
# real quando o usuário informado não existe. Ver User.consumir_tempo_de_verificacao.
_HASH_FALSO = ph.hash('hash-descartavel-para-igualar-o-tempo-de-resposta')

# Tabela associativa para relacionamento many-to-many entre User e TaskGroup
user_taskgroup = db.Table('user_taskgroup',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('taskgroup_id', db.Integer, db.ForeignKey('task_groups.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Administrador que cadastrou este usuário pela interface web. Fica nulo
    # para os administradores criados pelo script create_user.py. É o que
    # permite a um administrador gerenciar os usuários que ele mesmo criou,
    # mesmo antes de adicioná-los a algum grupo.
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_by = db.relationship('User', remote_side=[id], backref='usuarios_criados')

    # Relacionamento com tarefas
    tarefas = db.relationship('Tarefa', backref='usuario', lazy=True, cascade='all, delete-orphan')

    # Relacionamento com notas
    notes = db.relationship('Note', backref='usuario', lazy=True, cascade='all, delete-orphan')

    # Relacionamento many-to-many com grupos de tarefas
    task_groups = db.relationship('TaskGroup', secondary=user_taskgroup, backref=db.backref('members', lazy='dynamic'))

    def set_password(self, password):
        """
        Cria hash da senha usando Argon2id.
        Argon2 é o vencedor do Password Hashing Competition e oferece
        melhor proteção contra ataques de força bruta e rainbow tables.
        """
        self.password_hash = ph.hash(password)

    def check_password(self, password):
        """
        Verifica se a senha está correta usando Argon2.

        Captura VerificationError (que cobre VerifyMismatchError) e também
        InvalidHashError — esta última não deriva de VerificationError e é
        levantada quando o hash armazenado não está no formato Argon2, por
        exemplo um registro antigo gravado com outro algoritmo. Sem tratá-la
        o login devolveria erro 500 em vez de recusar a autenticação.
        """
        try:
            ph.verify(self.password_hash, password)
            return True
        except (VerificationError, InvalidHashError):
            return False

    def precisa_rehash(self):
        """Indica se o hash foi gerado com parâmetros Argon2 antigos."""
        try:
            return ph.check_needs_rehash(self.password_hash)
        except InvalidHashError:
            return True

    @staticmethod
    def consumir_tempo_de_verificacao():
        """
        Executa uma verificação Argon2 sobre um hash descartável.

        Usado no login quando o usuário não existe, para que a resposta leve o
        mesmo tempo de uma tentativa com usuário válido e não seja possível
        descobrir quais nomes estão cadastrados medindo o tempo de resposta.
        """
        try:
            ph.verify(_HASH_FALSO, 'senha-que-nunca-confere')
        except (VerificationError, InvalidHashError):
            pass

    def __repr__(self):
        return f'<User {self.username}>'


class TaskGroup(db.Model):
    __tablename__ = 'task_groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Relacionamento com o administrador do grupo
    admin = db.relationship('User', foreign_keys=[admin_id], backref='administered_groups')

    # Relacionamento com tarefas
    tarefas = db.relationship('Tarefa', backref='task_group', lazy=True, cascade='all, delete-orphan')

    # Relacionamento com notas
    notes = db.relationship('Note', backref='task_group', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<TaskGroup {self.name}>'


class ConteudoDeGrupo:
    """
    Regra de permissão comum aos conteúdos que vivem dentro de um grupo
    (compromissos e anotações).

    Quem pode alterar é o autor do conteúdo ou o administrador daquele grupo
    específico — o campo TaskGroup.admin_id. A flag global User.is_admin não
    entra na conta: ela apenas dá acesso à área administrativa, e usá-la aqui
    faria com que qualquer administrador do sistema, ao ser adicionado como
    membro de um grupo alheio, passasse a poder editar e apagar o conteúdo de
    todos os demais membros.
    """

    def pode_editar(self, usuario):
        if usuario is None or not usuario.is_authenticated:
            return False
        if self.user_id == usuario.id:
            return True
        return self.task_group is not None and self.task_group.admin_id == usuario.id


class Tarefa(ConteudoDeGrupo, db.Model):
    __tablename__ = 'tarefas'

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    task_group_id = db.Column(db.Integer, db.ForeignKey('task_groups.id'), nullable=False)

    def __repr__(self):
        return f'<Tarefa {self.id}: {self.data}>'


class Note(ConteudoDeGrupo, db.Model):
    __tablename__ = 'notes'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    task_group_id = db.Column(db.Integer, db.ForeignKey('task_groups.id'), nullable=False)

    def __repr__(self):
        return f'<Note {self.id}: {self.title}>'
