import sys
import os
# Adiciona o diretório raiz ao sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app import db

# Adaptador WSGI para Vercel
def handler(environ, start_response):
    return app.wsgi_app(environ, start_response)

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Cria as tabelas se não existirem
            
    app.run()

