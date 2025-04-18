import sys
import os

# Adiciona o diretório raiz ao sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import Categoria

app = create_app()

# Função para inserir categorias padrão
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
    print("✅ Categorias padrão inseridas!")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Cria as tabelas se não existirem

        """ if not Categoria.query.first():
            app.test_client().get('/populate') """
        
        # Insere categorias padrão
        if not Categoria.query.first():  # Só popula se estiver vazio
            populate_categorias()
            
    app.run(debug=True)

# Adaptador WSGI para Vercel
def handler(environ, start_response):
    return app.wsgi_app(environ, start_response)
