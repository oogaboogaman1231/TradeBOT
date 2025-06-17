import threading
import json
import time
from flask import Flask, render_template, jsonify, request, redirect, url_for, session, g
from werkzeug.security import check_password_hash # Para verificar senhas
import os # Para a chave secreta da sessão

# Importar as funções de auth e db
from auth import register_user, get_user_by_email, add_broker_config, get_user_broker_configs, get_openai_key_for_user, check_password
from db import get_db, close_db, init_app as init_db_app # Importar init_app do db

# Importar funções do main.py para iniciar/parar o bot
# Note: Estas serão referências às funções no escopo global de main.py
# A atribuição real ocorrerá no if __name__ == '__main__': em main.py
start_bot_for_user = None
stop_bot_for_user = None
bot_threads = {} # Manter o controle das threads do bot no app também
bot_stop_events = {} # Manter o controle dos eventos de parada no app também

# Flask App setup
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['DATABASE'] = 'database.db' # Define o nome do arquivo do banco de dados
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'sua_chave_secreta_padrao_muito_segura') # Use uma variável de ambiente ou uma chave forte

# Inicializa os Blueprints de db (para comandos CLI)
init_db_app(app)

# Global variables to store dashboard data (per user, in a real app, but for simplicity here)
# For a multi-user dashboard, this would need to be a dict indexed by user_id
dashboard_data_by_user = {} # {user_id: {status, usdt, portfolio, history}}

def get_user_dashboard_data(user_id):
    if user_id not in dashboard_data_by_user:
        dashboard_data_by_user[user_id] = {
            "status": "Aguardando início do bot...",
            "usdt": 0,
            "portfolio": {},
            "history": [],
            "next_cycle_time": 0
        }
    return dashboard_data_by_user[user_id]

def update_dashboard_data(user_id, new_data):
    current_data = get_user_dashboard_data(user_id)
    
    if "status" in new_data:
        current_data["status"] = new_data["status"]
    
    if "usdt" in new_data:
        current_data["usdt"] = new_data["usdt"]
    
    if "portfolio" in new_data:
        # A lógica de atualização do portfólio pode ser mais complexa
        # para garantir que os preços e quantidades sejam atualizados corretamente
        updated_portfolio_data = {}
        for symbol_pair, item_data in new_data["portfolio"].items():
            if symbol_pair in current_data["portfolio"]:
                # Atualiza item existente
                current_data["portfolio"][symbol_pair].update(item_data)
            else:
                # Adiciona novo item
                current_data["portfolio"][symbol_pair] = item_data
            updated_portfolio_data[symbol_pair] = current_data["portfolio"][symbol_pair]
        
        # Remove símbolos que não estão mais no portfólio e não são USDT (ou tem qte zero)
        keys_to_remove = [
            sym for sym, data in current_data["portfolio"].items()
            if sym not in updated_portfolio_data and sym != "USDT" and data.get("amount", 0) <= 0
        ]
        for key in keys_to_remove:
            del current_data["portfolio"][key]

        # Garante que USDT esteja sempre presente
        if "USDT" in new_data["portfolio"]:
            current_data["portfolio"]["USDT"] = new_data["portfolio"]["USDT"]
        elif "USDT" not in current_data["portfolio"]:
             current_data["portfolio"]["USDT"] = {"amount": 0, "current_price": 1.0}


    if "history" in new_data:
        for item in new_data["history"]:
            if len(current_data["history"]) >= 20:
                current_data["history"].pop(0)
            current_data["history"].append(item)
    
    if "next_cycle_time" in new_data:
        current_data["next_cycle_time"] = new_data["next_cycle_time"]

    print(f"[WEB DASHBOARD DATA UPDATED] for user {user_id}", current_data)


# --- Rotas de Autenticação e Principal ---

@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        # Em um app real, você buscaria o usuário do banco de dados
        # Aqui, apenas simulamos que o user_id é suficiente
        g.user = {"id": user_id, "email": session.get('user_email')}

@app.route('/')
def index():
    if g.user:
        # Se logado, renderiza o dashboard com os dados do usuário
        user_dashboard_data = get_user_dashboard_data(g.user['id'])
        return render_template('index.html', **user_dashboard_data)
    return redirect(url_for('login')) # Redireciona para login se não estiver logado

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        error = None

        user = get_user_by_email(email)

        if user is None:
            error = 'Email não registrado.'
        elif not check_password(user['password'], password):
            error = 'Senha incorreta.'

        if error is None:
            session.clear()
            session['user_id'] = user['id']
            session['user_email'] = user['email']
            return redirect(url_for('index'))
        
        return render_template('login.html', error=error, form_data=request.form)
    
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    email = request.form['email']
    password = request.form['password']
    binance_api_key = request.form['binance_api_key']
    binance_secret_key = request.form['binance_secret_key']
    openai_api_key = request.form['openai_api_key'] # Nova chave
    error = None

    if not email:
        error = 'Email é obrigatório.'
    elif not password:
        error = 'Senha é obrigatória.'
    elif not binance_api_key or not binance_secret_key:
        error = 'Chaves da Binance são obrigatórias.'
    elif not openai_api_key:
        error = 'Chave da OpenAI é obrigatória.'

    if error is None:
        try:
            # Registra o usuário
            user_id = register_user(email, password)
            
            # Adiciona a configuração da corretora e a chave da OpenAI
            add_broker_config(user_id, "Binance", binance_api_key, binance_secret_key, openai_api_key)

            session.clear()
            session['user_id'] = user_id
            session['user_email'] = email
            return redirect(url_for('index'))
        except ValueError as e:
            error = str(e) # Erro de usuário já existe
        except Exception as e:
            error = f"Erro ao registrar: {e}"

    return render_template('login.html', error=error, form_data=request.form)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/start_bot', methods=['POST'])
def start_bot_endpoint():
    global start_bot_for_user, stop_bot_for_user, bot_threads, bot_stop_events

    if not g.user:
        return jsonify({"status": "error", "message": "Usuário não autenticado."}), 401

    user_id = g.user['id']

    # Impede iniciar se já estiver rodando
    if user_id in bot_threads and bot_threads[user_id].is_alive():
        return jsonify({"status": "error", "message": f"Bot para o usuário {g.user['email']} já está rodando."}), 400

    if not start_bot_for_user:
        return jsonify({"status": "error", "message": "A função de iniciar o bot não está disponível."}), 500

    # Obter configurações do usuário do DB
    broker_configs = get_user_broker_configs(user_id)
    if not broker_configs:
        return jsonify({"status": "error", "message": "Nenhuma configuração de corretora encontrada para este usuário."}), 400

    # Supondo uma única configuração de corretora por enquanto
    broker_config = broker_configs[0]
    binance_api_key = broker_config['api_key']
    binance_secret_key = broker_config['secret_key']
    openai_api_key = broker_config['openai_api_key'] # Chave OpenAI do DB

    if not binance_api_key or not binance_secret_key or not openai_api_key:
        return jsonify({"status": "error", "message": "As chaves da API (Binance ou OpenAI) estão ausentes no seu perfil."}), 400

    # Construir o objeto config que o trade_logic.run_bot espera
    # As configurações como TRADE_INTERVAL_SECONDS virão de um config.json global
    # ou de padrões dentro do trade_logic. No entanto, as chaves de API específicas
    # do usuário são passadas diretamente.
    
    # É importante passar a config global_config do main.py para que o trade_logic tenha todos os padrões
    # Para isso, precisamos que main.py importe e forneça global_config
    
    # POR ENQUANTO, usaremos um placeholder para o global_config.
    # Em main.py, faremos start_bot_for_user = app.start_bot_for_user_func
    # e passaremos o global_config.

    # TEMPORÁRIO para que app.py possa chamar start_bot_for_user
    # O objeto config completo (com interval_seconds, quantity_per_trade etc.)
    # será construído no main.py e passado para o bot_runner
    # Aqui, passamos apenas as chaves para start_bot_for_user do main.py
    # que por sua vez, vai montar o config completo.

    # TODO: Refatorar start_bot_for_user em main.py para pegar as chaves do DB
    # e usar o global_config. A app.py só precisa chamar start_bot_for_user(user_id)
    # Isso já foi feito no main.py anterior.
    
    # A função start_bot_for_user em main.py já busca as chaves do DB e o global_config.
    # Não precisamos passá-las explicitamente aqui, apenas o user_id.
    success = start_bot_for_user(user_id) # Esta função é do main.py

    if success:
        get_user_dashboard_data(user_id)["status"] = f"Bot iniciado para {g.user['email']}. Aguardando ciclo..."
        return jsonify({"status": "success", "message": f"Bot iniciado para o usuário {g.user['email']}."}), 200
    else:
        return jsonify({"status": "error", "message": f"Falha ao iniciar o bot para o usuário {g.user['email']}. Verifique os logs."}), 500

@app.route('/stop_bot', methods=['POST'])
def stop_bot_endpoint():
    global start_bot_for_user, stop_bot_for_user, bot_threads, bot_stop_events

    if not g.user:
        return jsonify({"status": "error", "message": "Usuário não autenticado."}), 401

    user_id = g.user['id']

    if user_id not in bot_threads or not bot_threads[user_id].is_alive():
        return jsonify({"status": "error", "message": f"Bot para o usuário {g.user['email']} não está rodando."}), 400

    if not stop_bot_for_user:
        return jsonify({"status": "error", "message": "A função de parar o bot não está disponível."}), 500

    success = stop_bot_for_user(user_id) # Esta função é do main.py

    if success:
        get_user_dashboard_data(user_id)["status"] = f"Bot parado para {g.user['email']}."
        return jsonify({"status": "success", "message": f"Bot parado para o usuário {g.user['email']}."}), 200
    else:
        return jsonify({"status": "error", "message": f"Falha ao parar o bot para o usuário {g.user['email']}."}), 500


@app.route('/data')
def data():
    if not g.user:
        return jsonify({"status": "error", "message": "Usuário não autenticado."}), 401
    
    # Retorna os dados do dashboard específicos para o usuário logado
    return jsonify(get_user_dashboard_data(g.user['id']))

@app.route('/update_data', methods=['POST'])
def receive_bot_data():
    data = request.get_json()
    if data and 'user_id' in data: # O bot agora deve enviar o user_id
        user_id = data['user_id']
        update_dashboard_data(user_id, data)
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error", "message": "Invalid data or missing user_id"}), 400

def run_flask_app():
    # Remove debug=True para produção
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)