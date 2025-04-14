from functools import wraps
from flask import Blueprint, current_app, abort, render_template, request, redirect, url_for, flash
from app import db, login_manager, mail, API_KEY
from app.models import Transacao, Categoria, User
from datetime import datetime, timedelta
from flask_login import login_user, logout_user, current_user, login_required
from flask_mail import Message
from firebase_admin import auth as firebase_auth
from firebase_admin import firestore
import requests
import re


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
    try:
        # Lista todos os usuários do Firebase
        users = firebase_auth.list_users().iterate_all()
        return render_template('admin.html', users=users)
    except Exception as e:
        flash(f'Erro ao carregar usuários: {str(e)}', 'danger')
        return redirect(url_for('main.index'))


@main_routes.route('/promover-admin/<uid>')
@admin_required
def promover_admin(uid):
    try:
        firebase_auth.set_custom_user_claims(uid, {'admin': True})
        flash('Usuário promovido a admin com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro: {str(e)}', 'danger')
    return redirect(url_for('main.admin_panel'))

@main_routes.route('/remover-admin/<uid>')
@admin_required
def remover_admin(uid):
    try:
        firebase_auth.set_custom_user_claims(uid, {'admin': None})

        # Atualiza o usuário local (opcional)
        user = firebase_auth.get_user(uid)
        
        flash(f'{user.email} teve os privilégios de admin removidos!', 'success')

        # logging.info(f"ADMIN ACTION: {current_user.email} removeu admin de {user.email}")

    except Exception as e:
        flash(f'Erro ao remover privilégios: {str(e)}', 'danger')

    return redirect(url_for('main.admin_panel'))

# Rotas
@main_routes.route('/')
@login_required
def index():
    user_id_filtro = request.args.get('user_id')

    # Filtra transações de acordo com o tipo de usuário
    if current_user.is_admin and user_id_filtro:
        transacoes_query = Transacao.query.filter_by(user_id=user_id_filtro)
    else:
        transacoes_query = Transacao.query.filter_by(user_id=current_user.id) if not current_user.is_admin else Transacao.query

    ultimas_transacoes = transacoes_query.order_by(Transacao.data.desc()).limit(5).all()

    if current_user.is_admin:
        # saldo = db.session.query(db.func.sum(Transacao.valor)).scalar() or 0
        receitas = db.session.query(db.func.sum(Transacao.valor)).filter(Transacao.tipo == 'receita').scalar() or 0
        despesas = db.session.query(db.func.sum(Transacao.valor)).filter(Transacao.tipo == 'despesa').scalar() or 0
        saldo = receitas - despesas or 0
    else:
        receitas = transacoes_query.filter_by(tipo='receita').with_entities(db.func.sum(Transacao.valor)).scalar() or 0
        despesas = transacoes_query.filter_by(tipo='despesa').with_entities(db.func.sum(Transacao.valor)).scalar() or 0
        saldo = receitas - despesas or 0

    usuarios = []
    if current_user.is_admin:
        usuarios = firebase_auth.list_users().iterate_all()
    
    return render_template('index.html', 
                         transacoes=ultimas_transacoes,
                         usuarios=usuarios,
                         user_id_filtro=user_id_filtro,
                         saldo=saldo,
                         receitas=receitas,
                         despesas=despesas)

@login_manager.user_loader
def load_user(user_id):
    try:
        user_record = firebase_auth.get_user(user_id)

         # Verifica custom claims para admin
        is_admin = user_record.custom_claims.get('admin', False) if user_record.custom_claims else False

        # Busca dados no Firestore
        db_firestore = firestore.client()
        user_doc = db_firestore.collection('usuarios').document(user_id).get()
        
        return User(
            uid=user_record.uid, 
            email=user_record.email,
            name=user_doc.get('full_name') if user_doc.exists else "Usuário", 
            is_admin=is_admin)
    
    except Exception as e:
        print(f"Erro ao carregar usuário: {str(e)}")
        return None

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
                decoded_token = firebase_auth.verify_id_token(
                    data['idToken'],
                    clock_skew_seconds=60)
                
                user = load_user(decoded_token['uid'])
            
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
                    flash(f'Erro ao logar: {error_msg}, usuário não cadastrado', 'danger')
        
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
        full_name = request.form['fullname']
        email = request.form['email']
        password = request.form['password']

        # Validação da senha
        errors = []
        
        # Mínimo 6 caracteres
        if len(password) < 6:
            errors.append("A senha deve ter pelo menos 6 caracteres")
            
        # Pelo menos uma letra maiúscula
        if not re.search(r'[A-Z]', password):
            errors.append("A senha deve conter pelo menos uma letra maiúscula")
            
        # Pelo menos um caractere especial
        if not re.search(r'[^A-Za-z0-9]', password):
            errors.append("A senha deve conter pelo menos um caractere especial")
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('cadastrar.html', email=email)
          
        try:
            # Cria usuário no Firebase
            user = firebase_auth.create_user(
                email=email,
                password=password
            )
            # Salva nome no Firestore
            db_firestore = firestore.client()
            usuarios_ref = db_firestore.collection('usuarios')
            usuarios_ref.document(user.uid).set({
                'full_name': full_name,
                'email': email,
                'created_at': firestore.SERVER_TIMESTAMP
            })

            flash('Cadastro realizado com sucesso! Faça login.', 'success')
            return redirect(url_for('main.login'))
        
        except firebase_auth.EmailAlreadyExistsError:
            flash('Este email já está cadastrado.', 'danger')
        except Exception as e:
            # Rollback em caso de erro
            firebase_auth.delete_user(user.uid)
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

@main_routes.route('/transacoes')
@login_required
def listar_transacoes():
    user_id_filtro = request.args.get('user_id')

    if current_user.is_admin:
        if user_id_filtro:
            transacoes = Transacao.query.filter_by(user_id=user_id_filtro).order_by(Transacao.data.desc()).all()
        else:
            transacoes = Transacao.query.order_by(Transacao.data.desc()).all()
    else:
        transacoes = Transacao.query.filter_by(user_id=current_user.id).order_by(Transacao.data.desc()).all()
    
    usuarios = firebase_auth.list_users().iterate_all() if current_user.is_admin else []
    

    return render_template('transacoes.html', 
                           transacoes=transacoes, 
                           firebase_auth=firebase_auth,
                           usuarios=usuarios,
                           user_id_filtro=user_id_filtro)

@main_routes.route('/adicionar', methods=['GET', 'POST'])
@login_required
def adicionar_transacao():
    categorias = Categoria.query.all()
    
    if request.method == 'POST':
        descricao = request.form['descricao']
        valor = float(request.form['valor'])
        tipo = request.form['tipo']
        categoria_id = int(request.form['categoria'])
        # (antigo formato) data = datetime.strptime(request.form['data'], '%Y-%m-%d')
        data = datetime.strptime(request.form['data'], '%Y-%m-%dT%H:%M')
        
        nova_transacao = Transacao(
            user_id=current_user.id,
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

    user_id_filtro = request.args.get('user_id')
    usuarios = []

    try:
        # Verifica se é admin e aplica filtros
        if current_user.is_admin:
            usuarios = firebase_auth.list_users().iterate_all()
            base_query = Transacao.query
            
            # Valida o usuário do filtro
            if user_id_filtro:
                try:
                    firebase_auth.get_user(user_id_filtro)
                    base_query = Transacao.query.filter_by(user_id=user_id_filtro)
                except firebase_auth.UserNotFoundError:
                    flash('Usuário não encontrado', 'danger')
                    return redirect(url_for('main.resumo'))

        else:
            base_query = Transacao.query.filter_by(user_id=current_user.id)

        # Resumo por categoria (usando a base_query)
        resumo_categorias = (
            base_query.join(Categoria)
            .with_entities(
                Categoria.nome,
                db.func.sum(Transacao.valor).label('total')
            )
            .group_by(Categoria.nome)
            .all()
        )

        # Últimos 30 dias
        trinta_dias_atras = datetime.now() - timedelta(days=30)
        transacoes_recentes = (
            base_query
            .filter(Transacao.data >= trinta_dias_atras)
            .order_by(Transacao.data.desc())
            .all()
        )

        return render_template(
            'resumo.html',
            resumo_categorias=resumo_categorias,
            transacoes_recentes=transacoes_recentes,
            usuarios=usuarios,
            user_id_filtro=user_id_filtro,
            data_atual=datetime.now().strftime('%Y-%m-%d',),
            firebase_auth=firebase_auth
        )

    except Exception as e:
        flash('Ocorreu um erro ao gerar o resumo', 'danger')
        return redirect(url_for('main.index'))

@main_routes.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_transacao(id):
    transacao = Transacao.query.get_or_404(id)
    categorias = Categoria.query.all()

    if not (current_user.is_admin or transacao.user_id == current_user.id):
        abort(403)
    
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
    # Verifica se é dono ou admin
    if not (current_user.is_admin or transacao.user_id == current_user.id):
        abort(403)
    db.session.delete(transacao)
    db.session.commit()
    flash('Transação excluída com sucesso!', 'success')
    return redirect(url_for('main.listar_transacoes'))





