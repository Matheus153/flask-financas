import pandas as pd
import numpy as np
from app import create_app
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from statsmodels.tsa.statespace.sarimax import SARIMAX
from sqlalchemy.sql import text
from sqlalchemy.orm import aliased
from joblib import dump, load
from datetime import datetime, timedelta
import plotly.express as px
from app.models import Transacao, Categoria
from app import db
import os

class FinancialPredictor:
    def __init__(self, user_id):
        self.user_id = user_id
        self.model_dir = "models"
        self.model_path = os.path.join(self.model_dir, f"{user_id}_model.joblib")
        self._create_model_dir()
        self.feature_processor = None

    def _create_model_dir(self):
        os.makedirs(self.model_dir, exist_ok=True)

    def load_data(self, start_date, end_date):
        app = create_app()
        with app.app_context():
            try:
                # Query otimizada com conversão explícita de data
                query = db.session.query(
                    Transacao.data,
                    Transacao.valor,
                    Transacao.tipo,
                    Categoria.nome.label('categoria')
                ).join(Categoria, Transacao.categoria_id == Categoria.id)\
                 .filter(
                    Transacao.user_id == self.user_id,
                    Transacao.data.between(start_date, end_date)
                )
                # Debug: Verificar query gerada
                print("\n--- SQL QUERY ---")
                print(query.statement.compile(compile_kwargs={"literal_binds": True}))
                
                # Ler dados
                df = pd.read_sql(query.statement, db.engine)
                
                # Debug: Dados brutos
                print("\n--- DADOS BRUTOS ---")
                print(df.head())
                print("Tipos originais:")
                print(df.dtypes)

                # Converter timestamp se necessário
                if not df.empty and np.issubdtype(df['data'].dtype, np.integer):
                    print("\nConvertendo timestamp...")
                    df['data'] = pd.to_datetime(df['data'], unit='ns')  # Altere para 'ms' se necessário
                
                # Renomear coluna
                df = df.rename(columns={'data': 'date', 'valor': 'amount', 'categoria': 'categoria_nome'})
                
                # Debug: Dados convertidos
                print("\n--- DADOS CONVERTIDOS ---")
                print(df.head())
                print("Novos tipos:")
                print(df.dtypes)

                return self._engineer_features(df) if not df.empty else pd.DataFrame()

            except Exception as e:
                print(f"\nERRO NA CARGA: {str(e)}")
                return pd.DataFrame()

    def _engineer_features(self, df):
        try:
            # Verificação crítica de dados
            if 'date' not in df.columns:
                raise ValueError("Coluna 'date' não encontrada")
            
            # Garantir tipo datetime
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            
            # Remover datas inválidas
            initial_count = len(df)
            df = df.dropna(subset=['date'])
            print(f"\nRemovidas {initial_count - len(df)} linhas com datas inválidas")

            # Ordenar e criar features
            df = df.sort_values('date').reset_index(drop=True)
            df['day'] = df['date'].dt.day.astype('int16')
            df['month'] = df['date'].dt.month.astype('int16')
            df['year'] = df['date'].dt.year.astype('int16')
            df['weekday'] = df['date'].dt.weekday.astype('int16')

            # Codificação one-hot segura
            if self.feature_processor is None:
                from sklearn.preprocessing import OneHotEncoder
                self.feature_processor = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
                self.feature_processor.fit(df[['tipo', 'categoria_nome']])

            encoded = self.feature_processor.transform(df[['tipo', 'categoria_nome']])
            encoded_df = pd.DataFrame(
                encoded,
                columns=self.feature_processor.get_feature_names_out(),
                dtype='float32'
            )

            # Merge final
            final_df = pd.concat([df[['date', 'amount', 'day', 'month', 'year', 'weekday']], encoded_df], axis=1)
            
            # Debug: Dados processados
            print("\n--- DADOS PROCESSADOS ---")
            print(final_df.head(3))
            print("Tipos finais:")
            print(final_df.dtypes)
            
            return final_df.dropna()

        except Exception as e:
            print(f"\nERRO NO PROCESSAMENTO: {str(e)}")
            return pd.DataFrame()

    def train_predictive_model(self, data):
        try:

            # Treinar SARIMAX
            try:
                sarimax_model = SARIMAX(
                    data['amount'],
                    order=(1,1,1),
                    seasonal_order=(1,1,1,12),
                    enforce_stationarity=False
                ).fit(disp=False)
            except Exception as e:
                print(f"Erro SARIMAX: {str(e)}")
                sarimax_model = None

            # Converter para arrays numpy tipados
            X = data.drop(columns=['amount']).values.astype('float32')
            y = data['amount'].values.astype('float32')

            # Verificação de dimensionalidade
            if X.ndim != 2 or y.ndim != 1:
                raise ValueError(f"Dimensões inválidas - X: {X.shape}, y: {y.shape}")

            rf_model = RandomForestRegressor(
                n_estimators=100,
                random_state=42,
                verbose=1
            )
            rf_model.fit(X, y)

            # Salvar ambos os modelos
            model_bundle = {
                'sarimax': sarimax_model,
                'rf': rf_model,
                'feature_processor': self.feature_processor
            }
            dump(model_bundle, self.model_path)
            return True
            
        except Exception as e:
            print(f"\nERRO DETALHADO:\n{str(e)}")
            print("\nAMOSTRA DOS DADOS:")
            print(data.head())
            return False

    def generate_predictions(self, periods=6):
        try:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError("Modelo não encontrado - Treine primeiro")
            
            if self.data is None or self.data.empty:
                raise ValueError("Dados não carregados")

            models = load(self.model_path)
            last_date = pd.to_datetime(self.data['date']).max()  # Usa a coluna date
            
            # Prepara features futuras
            # Criar datas futuras
            future_dates = pd.date_range(
                start=last_date + pd.DateOffset(months=1),
                periods=periods,
                freq='M'
            )

            # Criar DataFrame de features futuras
            future_data = pd.DataFrame({'date': future_dates})
            future_data['day_of_week'] = future_data['date'].dt.dayofweek
            future_data['month'] = future_data['date'].dt.month
            future_data['year'] = future_data['date'].dt.year

            # Processar features categóricas
            if models['feature_processor']:
                future_encoded = models['feature_processor'].transform(
                    pd.DataFrame({'tipo': ['despesa']*periods, 'categoria_nome': ['Outros']*periods})
                )
                future_encoded = pd.DataFrame(
                    future_encoded,
                    columns=models['feature_processor'].get_feature_names_out()
                )
                future_data = pd.concat([future_data, future_encoded], axis=1)

            # Fazer previsões
            predictions = {}
            if models['sarimax']:
                predictions['sarimax'] = models['sarimax'].forecast(steps=periods)
            
            if models['rf']:
                rf_features = future_data.drop(columns=['date']).values.astype('float32')
                predictions['rf'] = models['rf'].predict(rf_features)

            # Combinar previsões
            if predictions:
                combined = pd.DataFrame(predictions)
                combined['date'] = future_dates
                combined['média'] = combined.mean(axis=1)
                return combined
            
            return None

        except Exception as e:
            print(f"Erro na previsão: {str(e)}")
            return None

    def descriptive_analysis(self, data):
        analysis = {
            'monthly_summary': data.groupby(pd.Grouper(freq='M')).agg({
                'amount': ['sum', 'mean', 'count']
            }),
            'category_distribution': data.groupby('categoria_nome')['amount'].sum(),
            'type_distribution': data.groupby('tipo')['amount'].sum()
        }
        return analysis

    def create_predictive_chart(self, data, predictions):
        try:
            if data.empty or 'date' not in data.columns:
                raise ValueError("Dados inválidos para visualização")

            # Gráfico histórico
            fig = px.line(
                data,
                x='date',
                y='amount',
                title='Histórico e Previsão Financeira',
                labels={'amount': 'Valor (R$)', 'date': 'Data'},
                template='plotly_white'
            )

            # Adicionar previsões se existirem
            if predictions is not None and not predictions.empty:
                fig.add_scatter(
                    x=predictions['date'],
                    y=predictions['média'],
                    mode='lines+markers',
                    name='Previsão',
                    line=dict(color='red', dash='dot')
                )

            fig.update_layout(
                xaxis_title='Data',
                yaxis_title='Valor (R$)',
                hovermode='x unified',
                showlegend=True
            )

            """ fig.update_xaxes(
                tickformat="%d/%m/%Y",
                rangeslider_visible=True
            ) """

            return fig

        except Exception as e:
            print(f"Erro na geração do gráfico: {str(e)}")
            return px.scatter(title='Erro na Visualização')
    
    @staticmethod
    def auto_train(user_id):
        try:
            predictor = FinancialPredictor(user_id)
            
            # Obter intervalo de datas real
            min_date = Transacao.query.with_entities(db.func.min(Transacao.data))\
                                .filter_by(user_id=user_id).scalar()
            max_date = Transacao.query.with_entities(db.func.max(Transacao.data))\
                                .filter_by(user_id=user_id).scalar()

            if min_date and max_date:
                data = predictor.load_data(min_date, max_date)
                
                if len(data) >= 10:
                    print(f"Iniciando treinamento automático para usuário {user_id}")
                    success = predictor.train_predictive_model(data)
                    if success:
                        print(f"Modelo atualizado para usuário {user_id}")
                    return success
            return False
            
        except Exception as e:
            print(f"Erro no auto-treinamento: {str(e)}")
            return False