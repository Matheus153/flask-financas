from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Transacao, Categoria
from datetime import datetime, timedelta

main_routes = Blueprint('main', __name__)

# Rotas
@main_routes.route('/')
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

@main_routes.route('/transacoes')
def listar_transacoes():
    transacoes = Transacao.query.order_by(Transacao.data.desc()).all()
    return render_template('transacoes.html', transacoes=transacoes)

@main_routes.route('/adicionar', methods=['GET', 'POST'])
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
def excluir_transacao(id):
    transacao = Transacao.query.get_or_404(id)
    db.session.delete(transacao)
    db.session.commit()
    flash('Transação excluída com sucesso!', 'danger')
    return redirect(url_for('main.listar_transacoes'))

# Rota para popular categorias iniciais (executar uma vez)
@main_routes.route('/populate')
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

