from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail, Message
from firebase_admin import credentials
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
import firebase_admin
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('API_KEY')

csrf = CSRFProtect()

login_manager = LoginManager()

db = SQLAlchemy()

mail = Mail()

migrate = Migrate()

firebase_config = {
        "type": os.getenv('TYPE'),
        "project_id": os.getenv('PROJECT_ID'),
        "private_key_id": os.getenv('PRIVATE_KEY_ID'),
        "private_key": os.getenv('PRIVATE_KEY').replace('\\n', '\n'),
        "client_email": os.getenv('CLIENT_EMAIL'),
        "client_id": os.getenv('CLIENT_ID'),
        "auth_uri": os.getenv('AUTH_URI'),
        "token_uri": os.getenv('TOKEN_URI'),
        "auth_provider_x509_cert_url": os.getenv('AUTH_PROVIDER_X509_CERT_URL'),
        "client_x509_cert_url": os.getenv('CLIENT_X509_CERT_URL'),
        "universe_domain": os.getenv('UNIVERSE_DOMAIN')
    }

cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred)

def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_SECRET_KEY'] = os.getenv('CSRF_SECRET_KEY')
    app.secret_key = os.getenv('SECRET_KEY')

    # Para usar nos links de direcionamentos de e-mail
    app.config['SERVER_NAME'] = 'localhost' # Substitua por 'localhost' caso queira rodar localmente
    app.config['PREFERRED_URL_SCHEME'] = 'http' # Substitua por 'http' caso queira rodar localmente
    app.config['APPLICATION_ROOT'] = '/'

    # Caso queira usar em ambiente local desmarque o comentario abaixo
    """ app.config['SERVER_NAME'] = 'localhost'
    app.config['PREFERRED_URL_SCHEME'] = 'http'
    app.config['APPLICATION_ROOT'] = '/' """

    # Configurações de Email
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')

    csrf.init_app(app)
    
    mail.init_app(app)

    # Configuracoes do Firebase # substituído por firebase_config
    """ firebase_config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # Sobe 2 níveis (de app/ para a raiz)
       'firebase-config.json'
    ) """

    # Desativar cache durante o desenvolvimento
    if app.config['DEBUG']:
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
        @app.after_request
        def add_header(response):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '-1'
            return response

    # Inicializar Flask-Login
    login_manager.init_app(app) 

    db.init_app(app)

    migrate.init_app(app, db)
    
    # Importar rotas após inicializar o app para evitar circular imports
    with app.app_context():
        from app.routes import main_routes
        app.register_blueprint(main_routes)

    return app