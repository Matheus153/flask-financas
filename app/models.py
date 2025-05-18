from app import db
from flask_login import UserMixin
from datetime import datetime

class User(UserMixin):
    def __init__(self, uid, email, name, is_admin=False, provider=None, primeiro_acesso=True):
        self.id = uid
        self.email = email
        self.name = name  # Novo campo
        self.is_admin = is_admin
        self.provider = provider  # 'google', 'github', etc
        self.primeiro_acesso = primeiro_acesso

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # 'receita' ou 'despesa'
    transacoes = db.relationship('Transacao', backref='categoria_rel', lazy=True)

class Transacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    data = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    tipo = db.Column(db.String(10), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    user_id = db.Column(db.String(128), nullable=False)  # Firebase UID do usuário

    # Novos campos para recorrência
    recorrente = db.Column(db.Boolean, default=False)
    meses_repeticao = db.Column(db.Integer, default=0)  # Contador de repetições
    data_original = db.Column(db.DateTime)  # Data da primeira ocorrência