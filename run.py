from app import create_app
from app.models import Categoria
from app import db

app = create_app()

def populate_categorias():
    """Função para inserir categorias padrão"""
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

    with app.app_context():  # Garante o contexto
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
            
    app.run(debug=True, port=3000)