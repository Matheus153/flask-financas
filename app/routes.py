from functools import wraps
from flask import Blueprint, abort, render_template, request, redirect, url_for, flash
from app import db, login_manager, mail, API_KEY
from app.models import Transacao, Categoria, User
from datetime import datetime, timedelta
from flask_login import login_user, logout_user, current_user, login_required
from flask_mail import Message
from firebase_admin import auth as firebase_auth
import requests


main_routes = Blueprint('main', __name__)

# Configurar LoginManager
login_manager.login_view = 'main.login'

# Função para promover usuário a admin
def make_admin(uid):
    firebase_auth.set_custom_user_claims(uid, {'is_admin': True})

def admin_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return func(*args, **kwargs)
    return decorated_view

@main_routes.route('/admin')
@login_required
@admin_required
def admin_panel():
    # Exemplo: Listar todos usuários
    users = firebase_auth.list_users().iterate_all()
    return render_template('admin.html', users=users)

# Rotas
@main_routes.route('/')
@login_required
def index():
    # Resumo financeiro
    transacoes = Transacao.query.order_by(Transacao.data.desc()).limit(5).all()
    # saldo = db.session.query(db.func.sum(Transacao.valor)).scalar() or 0
    receitas = db.session.query(db.func.sum(Transacao.valor)).filter(Transacao.tipo == 'receita').scalar() or 0
    despesas = db.session.query(db.func.sum(Transacao.valor)).filter(Transacao.tipo == 'despesa').scalar() or 0
    saldo = receitas - despesas or 0
    
    return render_template('index.html', 
                         transacoes=transacoes,
                         saldo=saldo,
                         receitas=receitas,
                         despesas=despesas)

@main_routes.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Configurações do Firebase
        FIREBASE_API_KEY = API_KEY # Encontre no Firebase Console
        
        # Endpoint de autenticação do Firebase
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
        
        payload = {
            "email": email,
            "password": password,
            "returnSecureToken": True
        }
        
        try:
            # Faz a requisição para a API do Firebase
            response = requests.post(url, json=payload)
            data = response.json()
            
            if response.status_code == 200:
                # Verifica o token JWT usando o Admin SDK
                decoded_token = firebase_auth.verify_id_token(data['idToken'])
                user_id = decoded_token['uid']
                
                # Busca informações adicionais do usuário
                user_record = firebase_auth.get_user(user_id)
                
                # Cria o objeto User para o Flask-Login
                user = User(uid=user_id, email=user_record.email, is_admin=False)
                login_user(user)
                
                flash('Login realizado com sucesso!', 'success')
                return redirect(url_for('main.index'))
            
            else:
                # Trata erros comuns
                error_msg = data.get('error', {}).get('message', 'Erro desconhecido')
                if error_msg == "INVALID_PASSWORD":
                    flash('Senha incorreta', 'danger')
                elif error_msg == "EMAIL_NOT_FOUND":
                    flash('Email não cadastrado', 'danger')
                else:
                    flash(f'Erro ao logar: {error_msg}', 'danger')
        
        except Exception as e:
            flash(f'Erro de conexão: {str(e)}', 'danger')
    
    return render_template('login.html')

@main_routes.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@main_routes.route('/cadastrar', methods=['GET', 'POST'])
def cadastrar():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        if len(password) < 6:
            flash('A senha deve ter pelo menos 6 caracteres', 'danger')
            return redirect(url_for('main.cadastrar'))
          
        try:
            # Cria usuário no Firebase
            user = firebase_auth.create_user(
                email=email,
                password=password
            )
            flash('Cadastro realizado com sucesso! Faça login.', 'success')
            return redirect(url_for('main.login'))
        
        except firebase_auth.EmailAlreadyExistsError:
            flash('Este email já está cadastrado.', 'danger')
        except Exception as e:
            flash('Erro ao cadastrar: ' + str(e), 'danger')
    
    return render_template('cadastrar.html')

@main_routes.route('/recuperar-senha', methods=['GET', 'POST'])
def recuperar_senha():
    if request.method == 'POST':
        email = request.form['email']
        
        try:
            # Gera link de redefinição
            link = firebase_auth.generate_password_reset_link(email)
            
            # Simulação de envio de email (implemente seu serviço de email aqui)
            # print(f'Link de redefinição: {link}')
            
            flash('Email de recuperação enviado! Verifique sua caixa postal.', 'success')

            msg = Message(
            'Redefinir Senha',
            sender='flaskfinances@gmail.com',
            recipients=[email]
            )
            msg.body = f'Clique para redefinir sua senha: {link}'
            mail.send(msg)

            return redirect(url_for('main.login'))
        
        except firebase_auth.UserNotFoundError:
            flash('Email não cadastrado.', 'danger')
        except Exception as e:
            flash('Erro ao enviar email: ' + str(e), 'danger')

    
    return render_template('recuperar_senha.html')

@login_manager.user_loader
def load_user(user_id):
    try:
        user_record = firebase_auth.get_user(user_id)
        return User(uid=user_record.uid, email=user_record.email)
    except:
        return None

@main_routes.route('/transacoes')
@login_required
def listar_transacoes():
    transacoes = Transacao.query.order_by(Transacao.data.desc()).all()
    return render_template('transacoes.html', transacoes=transacoes)

@main_routes.route('/adicionar', methods=['GET', 'POST'])
@login_required
def adicionar_transacao():
    categorias = Categoria.query.all()
    
    if request.method == 'POST':
        descricao = request.form['descricao']
        valor = float(request.form['valor'])
        tipo = request.form['tipo']
        categoria_id = int(request.form['categoria'])
        data = datetime.strptime(request.form['data'], '%Y-%m-%d')
        
        nova_transacao = Transacao(
            descricao=descricao,
            valor=valor,
            tipo=tipo,
            categoria_id=categoria_id,
            data=data
        )
        
        db.session.add(nova_transacao)
        db.session.commit()
        
        flash('Transação adicionada com sucesso!', 'success')
        return redirect(url_for('.index'))
    
    return render_template('adicionar.html', categorias=categorias, datetime=datetime)

@main_routes.route('/resumo')
@login_required
def resumo():
    # Agrupar por categoria
    resumo_categorias = db.session.query(
        Categoria.nome,
        db.func.sum(Transacao.valor).label('total')
    ).join(Transacao).group_by(Categoria.nome).all()
    
    # Últimos 30 dias
    trinta_dias_atras = datetime.now() - timedelta(days=30)
    transacoes_recentes = Transacao.query.filter(Transacao.data >= trinta_dias_atras).all()
    
    return render_template('resumo.html', 
                         resumo_categorias=resumo_categorias,
                         transacoes_recentes=transacoes_recentes)

@main_routes.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_transacao(id):
    transacao = Transacao.query.get_or_404(id)
    categorias = Categoria.query.all()
    
    if request.method == 'POST':
        transacao.descricao = request.form['descricao']
        transacao.valor = float(request.form['valor'])
        transacao.tipo = request.form['tipo']
        transacao.categoria_id = int(request.form['categoria'])
        transacao.data = datetime.strptime(request.form['data'], '%Y-%m-%d')
        
        db.session.commit()
        flash('Transação atualizada com sucesso!', 'success')
        return redirect(url_for('main.listar_transacoes'))
    
    return render_template('editar.html', 
                         transacao=transacao, 
                         categorias=categorias)

@main_routes.route('/excluir/<int:id>')
@login_required
def excluir_transacao(id):
    transacao = Transacao.query.get_or_404(id)
    db.session.delete(transacao)
    db.session.commit()
    flash('Transação excluída com sucesso!', 'danger')
    return redirect(url_for('main.listar_transacoes'))

# Rota para popular categorias iniciais (executar uma vez)
@main_routes.route('/populate')
@login_required
def populate_categorias():
    categorias_padrao = [
        {'nome': 'Salário', 'tipo': 'receita'},
        {'nome': 'Investimentos', 'tipo': 'receita'},
        {'nome': 'Alimentação', 'tipo': 'despesa'},
        {'nome': 'Moradia', 'tipo': 'despesa'},
        {'nome': 'Transporte', 'tipo': 'despesa'},
        {'nome': 'Lazer', 'tipo': 'despesa'},
        {'nome': 'Saúde', 'tipo': 'despesa'},
        {'nome': 'Educação', 'tipo': 'despesa'},
    ]
    
    for cat in categorias_padrao:
        if not Categoria.query.filter_by(nome=cat['nome']).first():
            nova_categoria = Categoria(nome=cat['nome'], tipo=cat['tipo'])
            db.session.add(nova_categoria)
    
    db.session.commit()
    return 'Categorias padrão adicionadas!'



