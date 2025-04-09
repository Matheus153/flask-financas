from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail, Message
import firebase_admin
from firebase_admin import credentials
import os
import dotenv

dotenv.load_dotenv()

API_KEY = os.getenv('API_KEY')

login_manager = LoginManager()

db = SQLAlchemy()

mail = Mail()

def create_app():
    app = Flask(__name__, template_folder='../templates')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(app.instance_path, "financas.db")}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.secret_key = os.getenv('SECRET_KEY')

    # Configurações de Email
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')

    mail.init_app(app)


    # Configuracoes do Firebase
    firebase_config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # Sobe 2 níveis (de app/ para a raiz)
       'firebase-config.json'
    )
    cred = credentials.Certificate(str(firebase_config_path))
    firebase_admin.initialize_app(cred)

    # Inicializar Flask-Login
    login_manager.init_app(app) 

    db.init_app(app)

    # Importar rotas após inicializar o app para evitar circular imports
    from app.routes import main_routes
    app.register_blueprint(main_routes)

    return app