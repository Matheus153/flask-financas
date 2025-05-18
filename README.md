
# Flask Finances

Um sistema que realiza seu controle financeiro através de acompanhamentos semanais e mensais dos seus lançamentos, aponta melhorias que poderiam ser realizadas e gera gráficos automaticamente com suas informações.

# Pré-requisitos

- Git (https://git-scm.com/)
- Python (https://www.python.org/)

# Instalação

Instale flask-financas com pip (gerenciador de pacotes do Python)

### Clonando repositório

```bash
  git clone https://github.com/Matheus153/flask-financas.git
```
### Acesse a pasta
```bash
  cd flask-financas
```
### Instale requisitos
```bash
  pip install -r requirements.txt
```

### Variáveis de ambiente
Para que o app funcione corretamente é necessário que existam variáveis de ambiente contendo informações sigilosas para execução do projeto. Estas variáveis se encontram contidas em arquivos (.env). 

Portanto, ao clonar o projeto crie um arquivo chamado ".env" na raiz do projeto e preenchar com os seguintes dados:

``` bash
  SECRET_KEY=chave_flask
  CSRF_SECRET_KEY=crie_sua_chave_propria
  SERVER_NAME=url_da_sua_aplicacao_em_producao_ou_escreva_localhost
  PREFERRED_URL_SCHEME=https_para_url_ou_http_para_localhost
  MAIL_USERNAME=seu_email
  MAIL_PASSWORD=senha_email
  API_KEY=chave_api_firebase
  TYPE=vem_do_arquivo_json_firebase
  PROJECT_ID=vem_do_arquivo_json_firebase
  PRIVATE_KEY_ID=vem_do_arquivo_json_firebase
  PRIVATE_KEY=vem_do_arquivo_json_firebase
  CLIENT_EMAIL=vem_do_arquivo_json_firebase
  CLIENT_ID=vem_do_arquivo_json_firebase
  AUTH_URI=vem_do_arquivo_json_firebase
  TOKEN_URI=vem_do_arquivo_json_firebase
  AUTH_PROVIDER_X509_CERT_URL=vem_do_arquivo_json_firebase
  CLIENT_X509_CERT_URL=vem_do_arquivo_json_firebase
  UNIVERSE_DOMAIN=vem_do_arquivo_json_firebase
  MESSAGING_SENDER_ID=disponivel_nas_configuracoes_projeto_firebase
  APP_ID=disponivel_nas_configuracoes_projeto_firebase
  SQLALCHEMY_DATABASE_URI=url_banco_de_dados
```

### Onde conseguir essas informações?

#### 1. Para as variáveis de e-mail:

🔐 Passo: Criar uma Senha de Aplicativo no Gmail

Obs: Primeiramente você deve criar ou já ter um e-mail disponível

O Gmail não permite mais o uso de senhas normais para aplicativos de terceiros. Você precisa gerar uma senha de aplicativo:

Acesse: **[Conta Google](https://myaccount.google.com/security)**

- Ative a Verificação em duas etapas (se ainda não tiver)

- Em Senhas de aplicativos, clique em "Selecionar aplicativo" → "Outro (Nome personalizado)"

- Digite um nome (ex: "Flask App") e clique em "Gerar"

- Copie a senha de 16 caracteres gerada (use-a no MAIL_PASSWORD)

#### 2. Para as variáveis Firebase

🔑 Passo: Obter a API Key do Firebase

Obs: Primeiramente você deve criar ou já ter um projeto no firebase console

- Acesse o Firebase **[Console](https://console.firebase.google.com/)**

- No projeto, clique em ⚙️ > Configurações do projeto

- Em Seus aplicativos, selecione o aplicativo web

- Copie a Chave da API (aparece como apiKey no config)

- Cole na variável ("API_KEY" do arquivo .env)

#### 3. SDK Admin Firebase

🔧 Como Gerar Corretamente SDK Admin Firebase:
Acesse o Firebase **[Console](https://console.firebase.google.com/)**

- Selecione seu projeto

- Vá em ⚙️ > Configurações do projeto > Contas de serviço

- Role para baixo e clique em Gerar nova chave privada

- Baixe o arquivo .json e preencha as variáveis de ambiente no arquivo .env

#### 4. Banco de dados PostgreSQL

Obs: Primeiramente você deve ter um banco de dados criado no **[Supabase](https://supabase.com/)** ou qualquer outra que disponibilize gratuitamente como (Heroku ou Railway)

🏦 Configurando banco de dados:

- Adicione uma tabela chamada "categoria" no banco de dados com as seguintes colunas:

  - **nome** (tipo: text)
  - **tipo** (tipo: text)

Você pode preenche-las com o seguinte padrão:

```bash
        {'nome': 'Salário', 'tipo': 'receita'},
        {'nome': 'Investimentos', 'tipo': 'receita'},
        {'nome': 'Alimentação', 'tipo': 'despesa'},
        {'nome': 'Moradia', 'tipo': 'despesa'},
        {'nome': 'Transporte', 'tipo': 'despesa'},
        {'nome': 'Lazer', 'tipo': 'despesa'},
        {'nome': 'Saúde', 'tipo': 'despesa'},
        {'nome': 'Educação', 'tipo': 'despesa'},
        {'nome': 'Impostos', 'tipo': 'despesa'},
        {'nome': 'Animais de estimação', 'tipo': 'despesa'},
        {'nome': 'Cartão de crédito', 'tipo': 'despesa'},
        {'nome': 'Vale-alimentação', 'tipo': 'receita'},
        {'nome': 'Vale-refeição', 'tipo': 'receita'},
```

- Adicione uma tabela chamada "transacao" no banco de dados com as seguintes colunas:

  - **descricao** (tipo: text)
  - **valor** (tipo: float8)
  - **data** (tipo: timestamp)
  - **tipo** (tipo: text)
  - **user_id** (tipo: text)
  - **categoria_id** (tipo: int8, foreign-key: categoria.id)
  - **recorrente** (tipo: bool)
  - **meses_repeticao** (tipo: int8)
  - **data_original** (tipo: timestamp)

- Clique em "Connect" e copie o link da url "transaction pooler" e cole na variável de ambiente (SQLALCHEMY_DATABASE_URI)

Exemplo de url:
```bash
postgresql+psycopg2://financas_app:NovaSenhaSuperSegura@localhost:5432/financas
```


## Start Server

Para iniciar o teste, execute o seguinte comando

```bash
  python run.py
```

## 🚀 Tech Stack

### 🧠 Backend

- **[Python](https://www.python.org/)** – linguagem principal do projeto.
- **[Flask](https://flask.palletsprojects.com/)** – microframework para criação da aplicação web e API.
- **[Flask-RESTful](https://flask-restful.readthedocs.io/en/latest/)** – estruturação de rotas RESTful.
- **[SQLAlchemy](https://www.sqlalchemy.org/)** – ORM para manipulação do banco de dados.

### 🖥️ Frontend (Provisório)

- **HTML5, CSS3, JavaScript**
- **Jinja2** – template engine integrada ao Flask.

### 🗄️ Banco de Dados

- **[PostgreSQL](https://www.postgresql.org/)** – recomendado para produção.
- **[SQLite](https://www.sqlite.org/index.html)** – opção leve para desenvolvimento e testes locais.

### 📁 Estrutura do diretório do projeto

```arduino
flask-financas/
├── app/
│   ├── __init__.py
│   ├── models.py
│   └── routes.py
├── templates/
│   ├── adicionar.html
│   ├── admin.html
│   ├── base.html
│   ├── cadastrar.html
│   ├── editar.html
│   ├── email_alerta.html
│   ├── email_recuperacao_senha.html
│   ├── index.html
│   ├── login.html
│   ├── perfil.html
│   ├── politica_privacidade.html
│   ├── recorrentes.html
│   ├── recuperar_senha.html
│   ├── redefinir_senha.html
│   ├── resumo.html
│   ├── termos_condicoes.html
│   ├── transacoes.html
│   └── tutorial.html
├── static/
│   ├── images/
│   │   └── favicon.ico
│   └── style.css
└── run.py
```

## Diagramas

<div align="center">	
  <h2>Fluxo controle de acesso</h2>
	<img src="public/fluxo-controle-de-acesso.png" width="400"/>
</div>

<div align="center">	
  <h2>Boas práticas</h2>
	<img src="public/boas-praticas.png" width="400"/>
</div>

## Autor 

<div align="center">
  <img width="150" src="https://avatars1.githubusercontent.com/u/62727591?s=460&u=03f8868eec3f187e0c33d7311b5bca386c8419c7&v=4">
  <h2>Matheus Santos Lima</h2>
</div>


