# Teste de engenharia de features
import pandas as pd
from app.ml_models import FinancialPredictor

# Dados de exemplo
data = {
    'date': ['2024-01-01', '2024-01-02', '2024-01-03'],
    'tipo': ['receita', 'despesa', 'receita'],
    'categoria_nome': ['salario', 'alimentacao', 'investimentos'],
    'amount': [5000.0, 150.0, 300.0]
}
df = pd.DataFrame(data)

predictor = FinancialPredictor('test_user')
processed_data = predictor._engineer_features(df)

print("Dados processados:")
print(processed_data.head())
