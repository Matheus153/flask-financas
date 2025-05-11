from app.models import Transacao
import pandas as pd

user_id = "9vWKAm1Pa5gcCanUpnxnWGWMmTv2"
from app import create_app
app = create_app()

with app.app_context():

    transacoes = Transacao.query.filter_by(user_id=user_id).all()
    print(f"Total de transações no banco: {len(transacoes)}")

    df_raw = pd.DataFrame([{
        'date': t.data,
        'amount': t.valor,
        'tipo': t.tipo,
        'categoria': t.categoria_id
    } for t in transacoes])

    print("\nDados brutos:")
    print(df_raw.head())
    print(f"\nPeríodo real: {df_raw['date'].min()} a {df_raw['date'].max()}")
