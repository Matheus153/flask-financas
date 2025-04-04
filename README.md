
# Flask Finances

Um sistema que realiza seu controle financeiro através de acompanhamentos semanais e mensais dos seus lançamentos, aponta melhorias que poderiam ser realizadas e gera gráfico automaticamente com suas informações.

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
│   ├── base.html
│   ├── editar.html
│   ├── index.html
│   ├── resumo.html
│   └── transacoes.html
├── static/
│   └── style.css
├── instance/
│   └── finances.db
└── run.py