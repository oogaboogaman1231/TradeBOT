# auth.py
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Blueprint, request, redirect, url_for, session, g
from db import get_db, close_db # Importar get_db e close_db

bp = Blueprint('auth', __name__, url_prefix='/auth')

# Função para inicializar o Blueprint em seu app Flask
def init_app(app):
    app.register_blueprint(bp)

@bp.route('/register', methods=('GET', 'POST'))
def register():
    # Esta rota agora será tratada pelo /register no app.py diretamente
    # Mantenho aqui apenas para estrutura se o app.py redirecionar para ela
    pass

@bp.route('/login', methods=('GET', 'POST'))
def login():
    # Esta rota agora será tratada pelo /login no app.py diretamente
    pass

# Funções auxiliares para o backend
def register_user(email, password):
    db = get_db()
    hashed_password = generate_password_hash(password)
    try:
        cursor = db.execute(
            "INSERT INTO users (email, password) VALUES (?, ?)",
            (email, hashed_password)
        )
        db.commit()
        return cursor.lastrowid # Retorna o ID do novo usuário
    except sqlite3.IntegrityError:
        raise ValueError(f"O usuário com o email '{email}' já existe.")
    except Exception as e:
        db.rollback()
        raise Exception(f"Erro ao registrar usuário: {e}")

def get_user_by_email(email):
    db = get_db()
    user = db.execute(
        "SELECT id, email, password FROM users WHERE email = ?", (email,)
    ).fetchone()
    return user

# NOVO: Função para verificar a senha do usuário
def check_password(hashed_password, password):
    return check_password_hash(hashed_password, password)

# ATUALIZADO: Função para adicionar/atualizar a configuração da corretora E A CHAVE DA OPENAI
def add_broker_config(user_id, broker_name, api_key, secret_key, openai_api_key):
    db = get_db()
    try:
        # Tenta inserir, se já existir (UNIQUE constraint), ele vai para o except
        db.execute(
            "INSERT INTO broker_configs (user_id, broker_name, api_key, secret_key, openai_api_key) VALUES (?, ?, ?, ?, ?)",
            (user_id, broker_name, api_key, secret_key, openai_api_key)
        )
        db.commit()
    except sqlite3.IntegrityError:
        # Se já existe, atualiza
        db.execute(
            "UPDATE broker_configs SET api_key = ?, secret_key = ?, openai_api_key = ? WHERE user_id = ? AND broker_name = ?",
            (api_key, secret_key, openai_api_key, user_id, broker_name)
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise Exception(f"Erro ao adicionar/atualizar configuração da corretora: {e}")

def get_user_broker_configs(user_id):
    db = get_db()
    configs = db.execute(
        "SELECT id, broker_name, api_key, secret_key, openai_api_key FROM broker_configs WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    return [dict(row) for row in configs] # Converte para lista de dicionários

# NOVO: Função para obter apenas a chave da OpenAI para um usuário
def get_openai_key_for_user(user_id):
    db = get_db()
    config = db.execute(
        "SELECT openai_api_key FROM broker_configs WHERE user_id = ? LIMIT 1",
        (user_id,)
    ).fetchone()
    return config['openai_api_key'] if config else None