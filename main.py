# main.py
import threading
import time
import os
import json
import requests
from dotenv import load_dotenv
import secrets # Importar o módulo secrets para gerar chaves seguras

# --- Função para garantir que FLASK_SECRET_KEY existe no .env ---
def ensure_flask_secret_key():
    env_path = '.env'
    secret_key_exists = False
    
    # Verifica se o arquivo .env existe e se a chave já está nele
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.strip().startswith('FLASK_SECRET_KEY='):
                    secret_key_exists = True
                    break
    
    # Se a chave não existir no .env, gera uma nova e a adiciona
    if not secret_key_exists:
        new_secret_key = secrets.token_hex(32) # Gera uma string hexadecimal de 64 caracteres (32 bytes)
        print(f"Gerando nova FLASK_SECRET_KEY e adicionando ao arquivo '{env_path}'...")
        with open(env_path, 'a') as f: # Abre em modo de adição para não sobrescrever o existente
            # Garante que a chave seja escrita em uma nova linha
            if os.path.exists(env_path) and os.path.getsize(env_path) > 0:
                with open(env_path, 'rb+') as f_check:
                    f_check.seek(-1, os.SEEK_END)
                    if f_check.read(1) != b'\n':
                        f.write('\n') # Adiciona uma nova linha se a última linha não terminar com uma
            f.write(f"FLASK_SECRET_KEY={new_secret_key}\n")
        print(f"FLASK_SECRET_KEY adicionada com sucesso ao '{env_path}'.")

# Chamar esta função ANTES de qualquer importação que possa depender da FLASK_SECRET_KEY
# ou de `load_dotenv()` no `app.py`. Isso garante que a chave esteja presente e carregada.
ensure_flask_secret_key()

# Agora, carregue as variáveis de ambiente (incluindo a recém-adicionada, se for o caso)
load_dotenv()

# Importar diretamente o objeto 'app' e variáveis globais do app.py
from app import app, run_flask_app, dashboard_data_by_user, bot_threads, bot_stop_events

# Importar módulos auxiliares (auth e db)
from auth import init_app as init_auth_app, get_user_broker_configs
from db import init_app as init_db_app, init_db

# Importar a lógica do bot
import trade_logic

# Inicializa os Blueprints e comandos CLI para a aplicação Flask
init_db_app(app)
init_auth_app(app)

# Carregar ou inicializar a configuração global do bot (não chaves de API, mas configurações como intervalos)
def load_global_config():
    config = {
        "TRADE_INTERVAL_SECONDS": 300, # 5 minutos
        "MAX_TRADES_PER_CYCLE": 1,
        "QUANTITY_PER_TRADE_USDT": 10,
        "symbols_to_watch": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT", "ADAUSDT", "FETUSDT", "AVAXUSDT", "OMUSDT", "RNDRUSDT", "TRUMPUSDT"] # Padrão, pode ser sobrescrito por config.json
    }
    if os.path.exists('config.json'):
        try:
            with open('config.json', 'r') as f:
                loaded_config = json.load(f)
                config.update(loaded_config)
                print("config.json carregado com sucesso para configurações globais do bot.")
        except json.JSONDecodeError:
            print("Erro ao ler config.json. Usando configurações padrão.")
        except Exception as e:
            print(f"Erro inesperado ao carregar config.json: {e}")
            
    return config

global_bot_config = load_global_config()

# --- Funções do Bot e Threads ---
# Estas são as funções reais que iniciarão/pararão o bot
def bot_runner(user_id, api_key, secret_key, openai_key, config, stop_event):
    user_config_for_bot = config.copy()
    user_config_for_bot["OPENAI_API_KEY"] = openai_key
    user_config_for_bot["BINANCE_API_KEY"] = api_key
    user_config_for_bot["BINANCE_SECRET_KEY"] = secret_key

    trade_logic.run_bot(user_id, api_key, secret_key, user_config_for_bot, stop_event, dashboard_data_by_user)

def start_bot_for_user(user_id):
    global bot_threads, bot_stop_events, global_bot_config # These are references from app.py

    broker_configs = get_user_broker_configs(user_id)
    if not broker_configs:
        print(f"Nenhuma configuração de corretora encontrada para o usuário {user_id}. O bot não pode iniciar.")
        return False

    broker_config = broker_configs[0] # Assumindo a primeira configuração
    api_key = broker_config['api_key']
    secret_key = broker_config['secret_key']
    openai_key = broker_config['openai_api_key'] # Obtém a chave da OpenAI do DB

    if not api_key or not secret_key or not openai_key:
        print(f"Chaves de API (Binance ou OpenAI) inválidas ou ausentes no banco de dados para o usuário {user_id}. O bot não pode iniciar.")
        return False

    if user_id in bot_threads and bot_threads[user_id].is_alive():
        print(f"Bot para o usuário {user_id} já está rodando.")
        return False

    stop_event = threading.Event()
    bot_stop_events[user_id] = stop_event
    
    bot_thread = threading.Thread(target=bot_runner, args=(user_id, api_key, secret_key, openai_key, global_bot_config, stop_event))
    bot_threads[user_id] = bot_thread
    bot_thread.start()
    print(f"Bot para o usuário {user_id} iniciado.")
    return True

def stop_bot_for_user(user_id):
    global bot_threads, bot_stop_events # These are references from app.py
    if user_id in bot_stop_events and not bot_stop_events[user_id].is_set():
        print(f"Parando bot para o usuário {user_id}...")
        bot_stop_events[user_id].set()
        if user_id in bot_threads:
            bot_threads[user_id].join(timeout=5)
            if bot_threads[user_id].is_alive():
                print(f"Aviso: Bot para o usuário {user_id} não terminou a tempo.")
            del bot_threads[user_id]
        del bot_stop_events[user_id]
        print(f"Bot para o usuário {user_id} parado.")
        return True
    print(f"Bot para o usuário {user_id} não está rodando ou já parado.")
    return False

# Conecta as funções de iniciar/parar bot do main.py com o app.py
app.start_bot_for_user = start_bot_for_user
app.stop_bot_for_user = stop_bot_for_user

# --- Ponto de entrada principal ---
if __name__ == '__main__':
    with app.app_context():
        # Inicializa o banco de dados se não existir
        if not os.path.exists(app.config['DATABASE']):
            print("Banco de dados não encontrado. Inicializando...")
            init_db()
            print("Banco de dados inicializado.")
        else:
            print("Banco de dados 'database.db' já existe. Pulando inicialização.")
            
    # Inicia o Flask app em uma thread separada
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()
    print("Flask app iniciado na thread separada e pronto para autenticação.")
    print("Acesse: http://127.0.0.1:5000")

    try:
        # Mantém a thread principal ativa para que as threads do bot e do Flask continuem
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDesligando a aplicação...")
        # Parar todos os bots ativos antes de sair
        for user_id in list(bot_threads.keys()):
            stop_bot_for_user(user_id)
        print("Aplicação encerrada.")
