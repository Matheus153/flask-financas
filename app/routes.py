from functools import wraps
from flask import Blueprint, abort, current_app, jsonify, render_template, request, redirect, url_for, flash
from app import db, login_manager, mail, API_KEY, create_app, cred, csrf
from app.models import Transacao, Categoria, User
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from flask_login import login_user, logout_user, current_user, login_required
from flask_mail import Message
from firebase_admin import auth as firebase_auth
from firebase_admin import firestore, exceptions as firebase_exceptions
from itsdangerous import URLSafeTimedSerializer
import firebase_admin
import plotly.express as px
import pandas as pd
import requests
import os
import re


main_routes = Blueprint('main', __name__)

# Configurar LoginManager
login_manager.login_view = 'main.login'

months = [
    (0, 'Todos os meses'),
    (1, 'Janeiro'),
    (2, 'Fevereiro'),
    (3, 'Março'),
    (4, 'Abril'),
    (5, 'Maio'),
    (6, 'Junho'),
    (7, 'Julho'),
    (8, 'Agosto'),
    (9, 'Setembro'),
    (10, 'Outubro'),
    (11, 'Novembro'),
    (12, 'Dezembro')
]

years = [(0, 'Todos os anos')] + [(year, year) for year in range(2020, datetime.now().year + 2)]

# Função de validação de senha reutilizável
def validar_senha(password):
    errors = []
    if len(password) < 6:
        errors.append("A senha deve ter pelo menos 6 caracteres")
    if not re.search(r'[A-Z]', password):
        errors.append("A senha deve conter pelo menos uma letra maiúscula")
    if not re.search(r'[^A-Za-z0-9]', password):
        errors.append("A senha deve conter pelo menos um caractere especial")
    if not re.search(r'[0-9]', password):
        errors.append("A senha deve conter pelo menos um número")
    return errors

# Função auxiliar para obter parâmetros de data
def get_filtro_data():
    selected_month = request.args.get('mes', datetime.now().month, type=int)
    selected_year = request.args.get('ano', datetime.now().year, type=int)
    return selected_month, selected_year

def verificar_saldos(app):
    with app.app_context():
        try:
            # Buscar todos os usuários
            users = firebase_auth.list_users().iterate_all()
            
            for user in users:
                uid = user.uid
                email = user.email
                
                # Calcular período do mês atual
                hoje = datetime.now()
                primeiro_dia_mes = hoje.replace(day=1, hour=0, minute=0, second=0)
                
                # Buscar transações do mês
                transacoes = Transacao.query.filter(
                    Transacao.user_id == uid,
                    Transacao.data >= primeiro_dia_mes
                ).all()
                
                # Calcular totais
                receitas = sum(t.valor for t in transacoes if t.tipo == 'receita')
                despesas = sum(t.valor for t in transacoes if t.tipo == 'despesa')
                saldo = receitas - despesas
                
                # Verificar condição de alerta
                if receitas > 0 and saldo < (receitas * 0.1):
                    enviar_alerta(email, user.display_name, receitas, despesas, saldo)
                    
        except Exception as e:
            print(f"Erro na verificação de saldos: {str(e)}")

def enviar_alerta(destinatario, nome, receitas, despesas, saldo):
    # Criar contexto manualmente
    with current_app.app_context():
        
        msg = Message(
            subject="Alerta Financeiro - Insight Finance",
            sender=os.getenv('MAIL_USERNAME'),
            recipients=[destinatario]
        )
        
        msg.html = render_template(
            'email_alerta.html',
            nome=nome,
            receitas=receitas,
            despesas=despesas,
            saldo=saldo,
            data=datetime.now().strftime('%d/%m/%Y')
        )
        
        try:
            mail.send(msg)
            print(f"Alerta enviado para {destinatario}")
        except Exception as e:
            print(f"Erro ao enviar alerta: {str(e)}")

# Inicializar agendador
scheduler_alerta = BackgroundScheduler()
scheduler_alerta.add_job(
    func=lambda: verificar_saldos(create_app()),
    trigger='cron',
    # day='last', (caso quisesse disparar no ultimo dia do mes)
    hour=11,
    minute=5
)
scheduler_alerta.start()

def criar_transacao_recorrente():
    app = create_app()

    # Verifica se o Firebase já foi inicializado
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(cred)

    with app.app_context():
        agora = datetime.now()
        
        # Busca transações recorrentes que ainda não completaram 12 meses
        transacoes = Transacao.query.filter(
            Transacao.recorrente == True,
            Transacao.meses_repeticao < 12
        ).all()

        for transacao in transacoes:
            # Calcula a próxima data (mesmo dia, mês seguinte)
            meses_a_adicionar = transacao.meses_repeticao + 1
            nova_data = transacao.data_original + relativedelta(months=meses_a_adicionar)

            # Verifica se já passou da data prevista
            if nova_data <= agora:
                nova_transacao = Transacao(
                    descricao=transacao.descricao,
                    valor=transacao.valor,
                    tipo=transacao.tipo,
                    categoria_id=transacao.categoria_id,
                    user_id=transacao.user_id,
                    data=nova_data,
                    recorrente=False, # Não permite recorrência em cascata
                    meses_repeticao=transacao.meses_repeticao + 1,
                    data_original=transacao.data_original
                )
            
                db.session.add(nova_transacao)
                transacao.meses_repeticao += 1
        
        db.session.commit()

# Agendador que roda diariamente às 00:01
scheduler_recorrentes = BackgroundScheduler()
scheduler_recorrentes.add_job(func=criar_transacao_recorrente, trigger='cron', hour=0, minute=5)
scheduler_recorrentes.start()

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

def configurar_primeiro_admin(uid):
    db_firestore = firestore.client()
    config_ref = db_firestore.collection('config').document('admin')
    
    # Transação atômica para evitar race conditions
    @firestore.transactional
    def atualizar_config(transaction):
        snapshot = config_ref.get(transaction=transaction)
        
        if not snapshot.exists:
            transaction.set(config_ref, {'primeiro_admin': uid})
            return True
        return False

    transaction = db_firestore.transaction()
    return atualizar_config(transaction)

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
    selected_month, selected_year = get_filtro_data()
    
    # Construir query base
    if current_user.is_admin:
        usuarios = firebase_auth.list_users().iterate_all()
        base_query = Transacao.query
        
        if user_id_filtro:
            base_query = base_query.filter_by(user_id=user_id_filtro)
    else:
        base_query = Transacao.query.filter_by(user_id=current_user.id)
        usuarios = []

    # Aplicar filtros de data
    if selected_month != 0:
        base_query = base_query.filter(
            db.extract('month', Transacao.data) == selected_month
        )
    
    if selected_year != 0:
        base_query = base_query.filter(
            db.extract('year', Transacao.data) == selected_year
        )

    # Cálculos usando a query base
    #saldo = se eu quisesse a soma de todos os lançamentos base_query.with_entities(db.func.sum(Transacao.valor)).scalar() or 0
    
    receitas = (
        base_query.filter_by(tipo='receita')
        .with_entities(db.func.sum(Transacao.valor))
        .scalar() or 0
    )
    despesas = (
        base_query.filter_by(tipo='despesa')
        .with_entities(db.func.sum(Transacao.valor))
        .scalar() or 0
    )

    saldo =  receitas - despesas or 0

    # Últimas transações
    ultimas_transacoes = (
        base_query.order_by(Transacao.data.desc())
        .limit(8)
        .all()
    )
    
    return render_template('index.html', 
                         transacoes=ultimas_transacoes,
                         usuarios=usuarios,
                         user_id_filtro=user_id_filtro,
                         saldo=saldo,
                         receitas=receitas,
                         despesas=despesas,
                         selected_month=selected_month,
                         selected_year=selected_year,
                         months = months,
                         years=years
                         )

@login_manager.user_loader
def load_user(user_id):
    try:
        user_record = firebase_auth.get_user(user_id)
        db_firestore = firestore.client()
        user_doc = db_firestore.collection('usuarios').document(user_id).get()

        user_data = user_doc.to_dict() if user_doc.exists else {}
        provider_data = user_record.provider_data[0] if user_record.provider_data else None
        
        return User(
            uid=user_record.uid,
            email=user_record.email,
            name=user_data.get('full_name', user_record.display_name),
            is_admin=user_data.get('admin', False),
            provider=provider_data.provider_id.split('.')[0] if provider_data else 'password',
            primeiro_acesso=user_data.get('primeiro_acesso', True)
        )

    except Exception as e:
        print(f"Erro ao carregar usuário: {str(e)}")
        return None

@main_routes.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Verifica se o e-mail já está registrado com provedor social
        try:
            # Verificar se já existe conta com este e-mail
            user_record = firebase_auth.get_user_by_email(email)

            # Se existir e for provedor social
            """ if any(provider.provider_id != 'password' for provider in user_record.provider_data):
                flash('Este e-mail está associado a um login social', 'warning')
                return redirect(url_for('main.login')) """
            
            # Verificar se existe provedor password
            if not any(p.provider_id == 'password' for p in user_record.provider_data):
                providers = [p.provider_id.split('.')[0] for p in user_record.provider_data]
                flash(f'Este e-mail está associado a um login social. Use login social com: {", ".join(providers)} ou redefina sua senha', 'warning')
                
                return redirect(url_for('main.login'))
                
        except firebase_auth.UserNotFoundError:
            pass  # Usuário não existe, prosseguir com login normal
        
        try:

            # Fluxo normal de login com email/senha
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
            payload = {
                "email": email,
                "password": password,
                "returnSecureToken": True
            }

            response = requests.post(url, json=payload)
            data = response.json()

            if response.status_code == 200:
                decoded_token = firebase_auth.verify_id_token(
                    data['idToken'],
                    clock_skew_seconds=60
                )

                user_id = decoded_token['uid']
                user = load_user(user_id)
                login_user(user)

                if user.primeiro_acesso:
                    return redirect(url_for('main.tutorial'))

                # Lógica de primeiro admin
                if configurar_primeiro_admin(user_id):
                    firebase_auth.set_custom_user_claims(
                        user_id, 
                        {'admin': True}
                    )

                flash('Login realizado com sucesso!', 'success')
                return redirect(url_for('main.index'))

            # Tratamento refinado de erros
            error_map = {
                'INVALID_PASSWORD': 'Senha incorreta',
                'EMAIL_NOT_FOUND': 'Email não cadastrado',
                'USER_DISABLED': 'Conta desativada',
                'INVALID_LOGIN_CREDENTIALS': 'Verifique se seu e-mail e senha estão corretos',
                'TOO_MANY_ATTEMPTS_TRY_LATER': 'Muitas tentativas. Tente mais tarde.'
            }
            
            error_code = data.get('error', {}).get('message', 'UNKNOWN_ERROR')
            flash(error_map.get(error_code, f'Erro no login: {error_code}'), 'danger')

        except firebase_auth.UserNotFoundError:
            flash('Email não cadastrado', 'danger')
        except firebase_auth.ErrorInfo as e:
            flash(f'Erro de autenticação: {str(e)}', 'danger')
        except Exception as e:
            flash(f'Erro inesperado: {str(e)}', 'danger')

    return render_template('login.html', os=os)

@main_routes.route('/login/social', methods=['POST'])
def login_social():
    try:
        id_token = request.json.get('token')
        decoded_token = firebase_auth.verify_id_token(
            id_token, 
            check_revoked=True, 
            clock_skew_seconds=60)
        user_id = decoded_token['uid']
        
        # Obter referência do Firestore
        db_firestore = firestore.client()
        user_ref = db_firestore.collection('usuarios').document(user_id)
        
        # Criar/Atualizar usuário
        user_data = {
            'email': decoded_token.get('email'),
            'full_name': decoded_token.get('name', 'Usuário'),
            'last_login': firestore.SERVER_TIMESTAMP,
            'provider': decoded_token.get('firebase', {}).get('sign_in_provider')
        }

        if not user_ref.get().exists:
            user_data.update({
                'created_at': firestore.SERVER_TIMESTAMP,
                'admin': False,
                'primeiro_acesso': True
            })
            user_ref.set(user_data)
            
            if configurar_primeiro_admin(user_id):
                user_ref.update({'admin': True})
        else:
            user_ref.update(user_data)

        user = load_user(user_id)
        login_user(user)
        
        return jsonify({
            'redirect': url_for('main.tutorial') if user.primeiro_acesso else url_for('main.index')
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 401
    

@main_routes.route('/tutorial', methods=['GET', 'POST'])
@login_required
def tutorial():
    if request.method == 'POST':
        try:
            db_firestore = firestore.client()
            db_firestore.collection('usuarios').document(current_user.id).update({
                'primeiro_acesso': False,
                'tutorial_completo_em': firestore.SERVER_TIMESTAMP
            })
            return redirect(url_for('main.index'))
        
        except Exception as e:
            flash(f'Erro ao salvar progresso: {str(e)}', 'danger')
    
    return render_template('tutorial.html')

@main_routes.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@main_routes.route('/cadastrar', methods=['GET', 'POST'])
def cadastrar():
    if request.method == 'POST':
        # Valide o CSRF token manualmente
        csrf.protect() 
        full_name = request.form['fullname']
        email = request.form['email']
        password = request.form['password']

        errors = validar_senha(password)
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('cadastrar.html', email=email)
          
        user = None  # Inicializa a variável
        try:
            # Tenta criar o usuário
            user = firebase_auth.create_user(
                email=email,
                password=password
            )
            
            # Salva no Firestore
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
            flash('Este email já está cadastrado.', 'warning')
            return redirect(url_for('main.cadastrar'))
            
        except Exception as e:
            # Faz rollback apenas se o usuário foi criado
            if user:
                firebase_auth.delete_user(user.uid)
            flash(f'Erro ao cadastrar: {str(e)}', 'danger')
            return redirect(url_for('main.cadastrar'))
    
    return render_template('cadastrar.html')

# Modifique a rota de recuperação de senha
@main_routes.route('/recuperar-senha', methods=['GET', 'POST'])
def recuperar_senha():
    if request.method == 'POST':
        email = request.form['email']
        
        try:
            # Verificar se o usuário existe
            user = firebase_auth.get_user_by_email(email)
            
            # Gerar token seguro com validade de 1 hora
            s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
            token = s.dumps(email, salt='password-reset')
            
            reset_link = url_for('main.redefinir_senha', token=token, _external=True)

            # Enviar email personalizado
            msg = Message(
            'Redefinição de Senha',
            sender=os.getenv('MAIL_USERNAME'),
            recipients=[email]
            )
            msg.html = render_template(
                'email_recuperacao_senha.html',
                reset_link=reset_link,
                data_solicitacao=datetime.now().strftime('%d/%m/%Y às %H:%M')
            )
            mail.send(msg)

            flash('Email de recuperação enviado! Verifique sua caixa de entrada e a pasta spam', 'success')
            return redirect(url_for('main.login'))

        except firebase_auth.UserNotFoundError:
            flash('Email não cadastrado.', 'danger')
        except Exception as e:
            flash(f'Erro ao enviar email: {str(e)}', 'danger')

    return render_template('recuperar_senha.html')

# Nova rota para redefinição de senha
@main_routes.route('/redefinir-senha/<token>', methods=['GET', 'POST'])
def redefinir_senha(token):
    try:
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        email = s.loads(token, salt='password-reset', max_age=3600)  # 1 hora de validade
    except:
        flash('Link inválido ou expirado. Solicite um novo link.', 'danger')
        return redirect(url_for('main.recuperar_senha'))

    if request.method == 'POST':
        nova_senha = request.form['password']
        confirmacao = request.form['confirm_password']

        # Validações
        if nova_senha != confirmacao:
            flash('As senhas não coincidem!', 'danger')
            return render_template('redefinir_senha.html', token=token)

        errors = validar_senha(nova_senha)
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('redefinir_senha.html', token=token)

        try:
            user = firebase_auth.get_user_by_email(email)
            
            # Verificar se a nova senha é diferente da atual
            try:
                # Tentativa de login com a nova senha para verificar se é igual
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
                response = requests.post(url, json={
                    "email": email,
                    "password": nova_senha,
                    "returnSecureToken": True
                })
                
                if response.status_code == 200:
                    flash('A nova senha não pode ser igual à senha atual', 'danger')
                    return render_template('redefinir_senha.html', token=token)
            except:
                pass

            # Atualizar senha se todas as validações passarem
            firebase_auth.update_user(user.uid, password=nova_senha)
            flash('Senha redefinida com sucesso! Faça login com a nova senha.', 'success')
            return redirect(url_for('main.login'))

        except firebase_auth.ErrorInfo as e:
            flash(f'Erro ao atualizar senha: {str(e)}', 'danger')
        except Exception as e:
            flash(f'Erro inesperado: {str(e)}', 'danger')

    return render_template('redefinir_senha.html', token=token)

@main_routes.route('/transacoes')
@login_required
def listar_transacoes():
    user_id_filtro = request.args.get('user_id')
    selected_month, selected_year = get_filtro_data()

    # Construir query base
    if current_user.is_admin:
        usuarios = firebase_auth.list_users().iterate_all()
        base_query = Transacao.query
        
        if user_id_filtro:
            base_query = base_query.filter_by(user_id=user_id_filtro)
    else:
        base_query = Transacao.query.filter_by(user_id=current_user.id)
        usuarios = []

    # Aplicar filtros de data
    if selected_month != 0:
        base_query = base_query.filter(
            db.extract('month', Transacao.data) == selected_month
        )
    
    if selected_year != 0:
        base_query = base_query.filter(
            db.extract('year', Transacao.data) == selected_year
        )
    
    transacoes = base_query.order_by(Transacao.data.desc()).all()

    return render_template('transacoes.html', 
                           transacoes=transacoes, 
                           firebase_auth=firebase_auth,
                           usuarios=usuarios,
                           user_id_filtro=user_id_filtro,
                           selected_month=selected_month,
                           selected_year=selected_year,
                           months=months,
                           years=years)

# Adicione esta rota para verificar transações recorrentes
@main_routes.route('/transacoes/recorrentes')
@login_required
def transacoes_recorrentes():
    user_id_filtro = request.args.get('user_id')
    
    # Construir query base
    if current_user.is_admin:
        usuarios = firebase_auth.list_users().iterate_all()
        base_query = Transacao.query.filter_by(recorrente=True)
        
        if user_id_filtro:
            try:
                firebase_auth.get_user(user_id_filtro)
                base_query = base_query.filter_by(user_id=user_id_filtro)
            except firebase_auth.UserNotFoundError:
                flash('Usuário não encontrado', 'danger')
                return redirect(url_for('main.transacoes_recorrentes'))
    else:
        base_query = Transacao.query.filter_by(
            user_id=current_user.id,
            recorrente=True
        )
        usuarios = []

    # Ordenar e obter resultados
    transacoes = base_query.order_by(Transacao.data.desc()).all()
    
    return render_template('recorrentes.html', 
                         transacoes=transacoes, 
                         relativedelta=relativedelta,
                         usuarios=usuarios,
                         user_id_filtro=user_id_filtro,
                         firebase_auth=firebase_auth)



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

        recorrente = 'recorrente' in request.form
        
        nova_transacao = Transacao(
            user_id=current_user.id,
            descricao=descricao,
            valor=valor,
            tipo=tipo,
            categoria_id=categoria_id,
            data=data,
            recorrente=recorrente,
            data_original=data if recorrente else None
        )
        
        db.session.add(nova_transacao)
        db.session.commit()
        
        flash('Transação adicionada com sucesso!', 'success')
        return redirect(url_for('.index'))
    
    return render_template('adicionar.html', categorias=categorias, datetime=datetime)



@main_routes.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_transacao(id):
    transacao = Transacao.query.get_or_404(id)
    categorias = Categoria.query.all()

    if not (current_user.is_admin or transacao.user_id == current_user.id):
        abort(403)

    if request.method == 'POST':
        try:
            csrf.protect()
            
            # Atualizar campos básicos
            transacao.descricao = request.form['descricao']
            transacao.valor = float(request.form['valor'])
            transacao.tipo = request.form['tipo']
            transacao.categoria_id = int(request.form['categoria'])
            transacao.data = datetime.strptime(request.form['data'], '%Y-%m-%dT%H:%M')

            novo_recorrente = 'recorrente' in request.form

            # Lógica de atualização de recorrência
            if transacao.recorrente and not novo_recorrente:
                # Desativar recorrência
                transacao.recorrente = False
                transacao.meses_repeticao = 0
                transacao.data_original = None
            elif not transacao.recorrente and novo_recorrente:
                # Ativar recorrência
                transacao.recorrente = True
                transacao.data_original = transacao.data  # Define data_original inicial
                transacao.meses_repeticao = 0

            # Sincroniza data_original se for recorrente e não disparada
            if transacao.recorrente and transacao.meses_repeticao == 0:
                transacao.data_original = transacao.data  # Mantém sempre atualizado

            db.session.commit()
            flash('Transação atualizada com sucesso!', 'success')
            return redirect(url_for('main.listar_transacoes'))

        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar: {str(e)}', 'danger')

    return render_template('editar.html', 
                         transacao=transacao, 
                         categorias=categorias)

@main_routes.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    try:
        db_firestore = firestore.client()
        user_ref = db_firestore.collection('usuarios').document(current_user.id)
        user_doc = user_ref.get()

        if request.method == 'POST':
            csrf.protect()
            
            novo_nome = request.form['nome'].strip()
            if not novo_nome:
                flash('O nome não pode estar vazio', 'danger')
                return redirect(url_for('main.perfil'))

            # Atualizar Firestore
            user_ref.update({'full_name': novo_nome})
            
            # Atualizar Firebase Auth (display name)
            firebase_auth.update_user(
                current_user.id,
                display_name=novo_nome
            )

            # Atualizar usuário na sessão
            user = load_user(current_user.id)
            login_user(user)

            flash('Nome atualizado com sucesso!', 'success')
            return redirect(url_for('main.perfil'))

        # Carregar dados atuais
        nome_atual = user_doc.get('full_name') if user_doc.exists else current_user.name

        return render_template('perfil.html', 
                            nome_atual=nome_atual,
                            provider=current_user.provider)

    except Exception as e:
        flash(f'Erro ao atualizar perfil: {str(e)}', 'danger')
        return redirect(url_for('main.perfil'))

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


@main_routes.route('/resumo')
@login_required
def resumo():
    graficos = {}
    resumo_categorias = []
    transacoes_recentes = []
    usuarios = []
    user_id_filtro = request.args.get('user_id')
    selected_month, selected_year = get_filtro_data()

    try:
         # Construir query base
        if current_user.is_admin:
            usuarios = firebase_auth.list_users().iterate_all()
            base_query = Transacao.query
            
            if user_id_filtro:
                base_query = base_query.filter_by(user_id=user_id_filtro)
        else:
            base_query = Transacao.query.filter_by(user_id=current_user.id)

        # Aplicar filtros de data
        if selected_month != 0:
            base_query = base_query.filter(
                db.extract('month', Transacao.data) == selected_month
            )
        
        if selected_year != 0:
            base_query = base_query.filter(
                db.extract('year', Transacao.data) == selected_year
            )

        # Resumo por categoria
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
        """ trinta_dias_atras = datetime.now() - timedelta(days=30)
        transacoes_recentes = (
            base_query
            .filter(Transacao.data >= trinta_dias_atras)
            .order_by(Transacao.data.desc())
            .all()
        ) """

        transacoes_recentes = (
            base_query
            .order_by(Transacao.data.desc())
            .limit(6)
            .all()
        )

        # Criar DataFrame para análise
        df = pd.DataFrame([{
            'Categoria': t.categoria_rel.nome,
            'Valor': t.valor,
            'Tipo': t.tipo,
            'Data': t.data
        } for t in transacoes_recentes])

        # Gráfico 1: Despesas por Categoria
        if not df.empty and 'despesa' in df['Tipo'].values:
            fig_despesas = px.pie(
                df[df['Tipo'] == 'despesa'],
                names='Categoria',
                values='Valor',
                title='Distribuição de Despesas por Categoria',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig_despesas.update_layout(font=dict(family="Poppins, sans-serif"))

            graficos['despesas'] = fig_despesas.to_html(full_html=False)
        else:
            pass

        # Gráfico 2: Comparativo Receitas vs Despesas
        if not df.empty and len(df['Tipo'].unique()) > 0:
            df_agg = df.groupby('Tipo', as_index=False).agg({'Valor': 'sum'})
            df_agg = df_agg.sort_values(by='Valor', ascending=False)
            
            if not df_agg.empty:
                df_agg['Valor_formatado'] = df_agg['Valor'].apply(
                    lambda x: f"{x:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )

                fig_comparativo = px.bar(
                    df_agg,
                    x='Tipo',
                    y='Valor',
                    title='Receitas vs Despesas',
                    color='Tipo',
                    text='Valor_formatado',
                    color_discrete_map={
                        'receita': '#57C7A2',
                        'despesa': '#F06960'
                    }
                )
                fig_comparativo.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    yaxis_title='Valor em (R$)',
                    font=dict(family="Poppins, sans-serif")
                )

                fig_comparativo.update_traces(
                    textposition='outside',
                    textfont_size=10
                )

                # Substituir os valores do eixo y por strings formatadas ao estilo brasileiro
                ticks = df_agg['Valor'].max()
                tick_vals = list(range(0, int(ticks) + 1, int(ticks / 5)))  # 5 ticks
                tick_text = [f"{v:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".") for v in tick_vals]

                fig_comparativo.update_yaxes(
                    tickformat=',.0f',
                    tickvals=tick_vals,
                    ticktext=tick_text,             # Sem casas decimais, com separador de milhar
                    separatethousands=True
                )

                graficos['comparativo'] = fig_comparativo.to_html(full_html=False)
            else:
                pass
        else:
            pass

    except Exception as e:
        flash(f'Ocorreu um erro ao gerar o resumo: {str(e)}', 'danger')
        return redirect(url_for('main.index'))

    return render_template(
        'resumo.html',
        resumo_categorias=resumo_categorias,
        transacoes_recentes=transacoes_recentes,
        usuarios=usuarios,
        user_id_filtro=user_id_filtro,
        data_atual=datetime.now().strftime('%Y-%m-%d'),
        firebase_auth=firebase_auth,
        graficos=graficos,
        selected_month=selected_month,
        selected_year=selected_year,
        months=months,
        years=years
    )