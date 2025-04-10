from app import create_app
from app.models import Categoria
from app import db

app = create_app()

from app.routes import load_user

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Cria as tabelas se não existirem

        if not Categoria.query.first():
            app.test_client().get('/populate')
            
    app.run(debug=True, port=3000)