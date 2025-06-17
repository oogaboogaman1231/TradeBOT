# main.py
import threading
import time
import os
import json
import requests
from dotenv import load_dotenv

# Importar as funções e o app do app.py
from app import run_flask_app, app, dashboard_data_by_user, start_bot_for_user as app_start_bot_func, stop_bot_for_user as app_stop_bot_func, bot_threads as app_bot_threads, bot_stop_events as app_bot_stop_events
import trade_logic
from auth import init_app as init_auth_app, get_user_broker_configs, get_user_by_email # remove register_user, add_broker_config
from db import init_app as init_db_app, init_db

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Inicializa os Blueprints e comandos CLI para a aplicação Flask
init_db_app(app)
init_auth_app(app)

# Define a SECRET_KEY do Flask para uso em sessões
# É crucial que esta chave seja definida antes de qualquer operação de sessão!
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'uma_chave_secreta_padrao_muito_segura_e_longa_para_dev')
if app.config['SECRET_KEY'] == 'uma_chave_secreta_padrao_muito_segura_e_longa_para_dev':
    print("AVISO: Usando chave secreta padrão do Flask. Por favor, defina FLASK_SECRET_KEY no seu .env para produção.")


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
# Estas são as referências que o app.py irá usar para interagir com os bots
bot_threads = app_bot_threads # Usar o dicionário de threads do app.py
bot_stop_events = app_bot_stop_events # Usar o dicionário de eventos de parada do app.py

def bot_runner(user_id, api_key, secret_key, openai_key, config, stop_event):
    # Aqui passamos a chave da OpenAI que é específica do usuário
    user_config_for_bot = config.copy()
    user_config_for_bot["OPENAI_API_KEY"] = openai_key
    user_config_for_bot["BINANCE_API_KEY"] = api_key # para trade_logic, que ainda pode usar isso
    user_config_for_bot["BINANCE_SECRET_KEY"] = secret_key # para trade_logic

    trade_logic.run_bot(user_id, api_key, secret_key, user_config_for_bot, stop_event, dashboard_data_by_user)

def start_bot_for_user(user_id):
    global bot_threads, bot_stop_events, global_bot_config

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
    
    # Passa o global_bot_config e as chaves específicas do usuário para o bot_runner
    bot_thread = threading.Thread(target=bot_runner, args=(user_id, api_key, secret_key, openai_key, global_bot_config, stop_event))
    bot_threads[user_id] = bot_thread
    bot_thread.start()
    print(f"Bot para o usuário {user_id} iniciado.")
    return True

def stop_bot_for_user(user_id):
    global bot_threads, bot_stop_events
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
# Isso permite que as rotas Flask em app.py chamem estas funções
app_start_bot_func.__globals__['start_bot_for_user'] = start_bot_for_user
app_stop_bot_func.__globals__['stop_bot_for_user'] = stop_bot_for_user

# --- Ponto de entrada principal ---
if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists(app.config['DATABASE']):
            print("Banco de dados não encontrado. Inicializando...")
            init_db()
            print("Banco de dados inicializado.")
        else:
            print("Banco de dados 'database.db' já existe. Pulando inicialização.")
        
        # REMOVIDO: A criação de usuário de teste e as configurações de broker não acontecem mais aqui.
        # Agora, tudo isso será feito via o formulário de registro/login no dashboard web.

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
        for user_id in list(bot_threads.keys()):
            stop_bot_for_user(user_id)
        print("Aplicação encerrada.")