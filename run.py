from app import create_app
from app import db

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Cria as tabelas se não existirem
            
    app.run()