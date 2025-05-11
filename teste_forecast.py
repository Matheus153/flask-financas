# Teste manual no shell
import numpy as np
import pandas as pd
from app.ml_models import FinancialPredictor


test_data = pd.DataFrame({
    'date': pd.date_range(start='2023-01-01', periods=12, freq='ME'),
    'amount': np.random.uniform(1000, 5000, 12),
    'tipo': ['receita', 'despesa']*6
})

predictor = FinancialPredictor('test_user')
predictor.train_predictive_model(test_data)
forecast = predictor.generate_forecast(test_data)

print("Previsões geradas:")
print(forecast[['date', 'media_receita', 'media_despesa']])