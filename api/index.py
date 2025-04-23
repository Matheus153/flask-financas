import sys
import os
# Adiciona o diretório raiz ao sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app

# Adaptador WSGI para Vercel
def handler(environ, start_response):
    return app.wsgi_app(environ, start_response)

app = create_app()

if __name__ == '__main__':
            
    app.run()

