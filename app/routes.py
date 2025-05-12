from functools import wraps
from flask import Blueprint, abort, jsonify, render_template, request, redirect, url_for, flash
from app import db, login_manager, mail, API_KEY, create_app, cred, csrf
from app.models import Transacao, Categoria, User
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from flask_login import login_user, logout_user, current_user, login_required
from flask_mail import Message
from firebase_admin import auth as firebase_auth
from firebase_admin import firestore
import firebase_admin
import plotly.express as px
import pandas as pd
import requests
import os
import re


main_routes = Blueprint('main', __name__)

# Configurar LoginManager
login_manager.login_view = 'main.login'

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
scheduler = BackgroundScheduler()
scheduler.add_job(func=criar_transacao_recorrente, trigger='cron', hour=0, minute=5)
scheduler.start()

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
    
    # Construir query base
    if current_user.is_admin:
        usuarios = firebase_auth.list_users().iterate_all()
        base_query = Transacao.query
        
        if user_id_filtro:
            try:
                firebase_auth.get_user(user_id_filtro)
                base_query = base_query.filter_by(user_id=user_id_filtro)
            except firebase_auth.UserNotFoundError:
                flash('Usuário não encontrado', 'danger')
                return redirect(url_for('main.index'))
    else:
        base_query = Transacao.query.filter_by(user_id=current_user.id)
        usuarios = []

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
                         despesas=despesas)

@login_manager.user_loader
def load_user(user_id):
    try:
        user_record = firebase_auth.get_user(user_id)

        # Determina o provedor
        # provider = 'email'

        if user_record.provider_data:
            provider = user_record.provider_data[0].provider_id.split('.')[0] if user_record.provider_data else 'password'

         # Verifica custom claims para admin
        is_admin = user_record.custom_claims.get('admin', False) if user_record.custom_claims else False

        # Busca dados no Firestore
        db_firestore = firestore.client()
        user_doc = db_firestore.collection('usuarios').document(user_id).get()
        
        return User(
            uid=user_record.uid, 
            email=user_record.email,
            name=user_doc.get('full_name') if user_doc.exists else user_record.display_name, 
            is_admin=is_admin,
            provider=provider
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
            if any(provider.provider_id != 'password' for provider in user_record.provider_data):
                flash('Este e-mail está associado a um login social', 'warning')
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
        decoded_token = firebase_auth.verify_id_token(id_token)
        user_id = decoded_token['uid']
        
        # Obter referência do Firestore
        db_firestore = firestore.client()
        user_ref = db_firestore.collection('usuarios').document(user_id)
        
        # Verificar se o usuário já existe
        if not user_ref.get().exists:
            # Criar novo documento com dados do provedor social
            user_data = {
                'created_at': firestore.SERVER_TIMESTAMP,
                'email': decoded_token.get('email'),
                'full_name': decoded_token.get('name') or 'Usuário',
                'provider': decoded_token.get('firebase', {}).get('sign_in_provider'),
                'admin': False
            }
            user_ref.set(user_data)
        
            # Verifica se é o primeiro usuário
            if configurar_primeiro_admin(user_id):
                user_ref.update({'admin': True})
        
        # Carregar e logar usuário
        user = load_user(user_id)
        login_user(user)
        
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 401

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

@main_routes.route('/recuperar-senha', methods=['GET', 'POST'])
def recuperar_senha():
    if request.method == 'POST':
        email = request.form['email']
        
        try:
            # Gera link de redefinição
            link = firebase_auth.generate_password_reset_link(email)
            
            # Simulação de envio de email (implemente seu serviço de email aqui)
            # print(f'Link de redefinição: {link}')
            flash('Email de recuperação enviado! Verifique sua caixa de entrada e a pasta de spam.', 'success')

            msg = Message(
            'Redefinição de Senha',
            sender=os.getenv('MAIL_USERNAME'),
            recipients=[email]
            )
            msg.body = f"Olá, Recebemos uma solicitação para redefinir a senha da sua conta em nossa plataforma.\n\nPara continuar com a redefinição, clique no link abaixo ou copie e cole o endereço em seu navegador:\n\n{link}\n\nApós concluir o processo, você poderá definir uma nova senha para acessar sua conta com segurança.\n\nSe você não solicitou esta alteração, por favor, ignore este e-mail. Sua conta continuará segura.\n\nAtenciosamente, Equipe Insight Finance!\n\nEste é um e-mail automático. Por favor, não responda diretamente a esta mensagem. Adicione nosso endereço aos seus contatos para garantir o recebimento de nossos comunicados."
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
        transacao.descricao = request.form['descricao']
        transacao.valor = float(request.form['valor'])
        transacao.tipo = request.form['tipo']
        transacao.categoria_id = int(request.form['categoria'])
        transacao.data = datetime.strptime(request.form['data'], '%Y-%m-%dT%H:%M')

        # Segurança para não permitir alterações em transações recorrentes
        if transacao.meses_repeticao > 0 and transacao.data_original != transacao.data:
            flash('Não é possível alterar a data de transações recorrentes já geradas', 'warning')
            return redirect(url_for('main.editar_transacao', id=id))
        
         # Atualiza recorrência
        novo_recorrente = 'recorrente' in request.form
        
        if transacao.recorrente and not novo_recorrente:
            # Se estava ativo e foi desativado
            transacao.recorrente = False
            transacao.meses_repeticao = 0
            transacao.data_original = None
        elif not transacao.recorrente and novo_recorrente:
            # Se estava inativo e foi ativado
            transacao.recorrente = True
            transacao.data_original = transacao.data
            transacao.meses_repeticao = 0
        
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


@main_routes.route('/resumo')
@login_required
def resumo():
    graficos = {}
    resumo_categorias = []
    transacoes_recentes = []
    usuarios = []
    user_id_filtro = request.args.get('user_id')

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
        trinta_dias_atras = datetime.now() - timedelta(days=30)
        transacoes_recentes = (
            base_query
            .filter(Transacao.data >= trinta_dias_atras)
            .order_by(Transacao.data.desc())
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
        graficos=graficos
    )