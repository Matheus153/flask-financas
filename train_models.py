from app import create_app, db
from app.models import Transacao, Categoria
from app.ml_models import FinancialPredictor
from datetime import datetime

app = create_app()

with app.app_context():
    # Treinar para todos os usuários com transações
    users = db.session.query(Transacao.user_id.distinct()).all()
    
    for user_id in users:
        user_id = user_id[0]
        print(f"Treinando modelo para usuário: {user_id}")
        
        predictor = FinancialPredictor(user_id)
        data = predictor.load_data(datetime(1900, 1, 1), datetime.now())
        
        if len(data) >= 10:
            predictor.train_predictive_model(data)
            print(f"Modelo treinado para {user_id} com {len(data)} registros")
        else:
            print(f"Dados insuficientes para {user_id} ({len(data)} registros)")