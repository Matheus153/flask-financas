from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os

db = SQLAlchemy()

def create_app():
    app = Flask(__name__, template_folder='../templates')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(app.instance_path, "financas.db")}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.secret_key = 'sua_chave_secreta_aqui'

    db.init_app(app)

    # Importar rotas após inicializar o app para evitar circular imports
    from app.routes import main_routes
    app.register_blueprint(main_routes)

    return app