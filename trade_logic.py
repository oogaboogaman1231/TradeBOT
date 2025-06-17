import time
import json
import requests
import os
import re
from datetime import datetime

from binance_api import BinanceAPI
from chatgpt_api import OpenAIAPI

# Endpoint para o dashboard Flask
FLASK_DASHBOARD_URL = "http://127.0.0.1:5000/update_data"

# A variável global_config será populada pela função run_bot
global_config = {}

# ATUALIZADO: A função agora aceita user_id
def send_to_dashboard(user_id, data):
    """Envia dados atualizados para o dashboard Flask, incluindo user_id."""
    data_with_user_id = data.copy()
    data_with_user_id['user_id'] = user_id # Adiciona o user_id
    try:
        response = requests.post(FLASK_DASHBOARD_URL, json=data_with_user_id) # Envia com user_id
        response.raise_for_status() # Lança exceções para status de erro (4xx ou 5xx)
    except requests.exceptions.ConnectionError:
        print(f"[DASHBOARD ERRO] Não foi possível conectar ao dashboard Flask para user {user_id}. Ele está rodando?")
    except requests.exceptions.RequestException as e:
        print(f"[DASHBOARD ERRO] Erro ao enviar dados ao dashboard Flask para user {user_id}: {e}")

def get_binance_balance_and_portfolio(binance_api, symbols_to_watch):
    """
    Obtém saldo em USDT e portfólio de criptomoedas com preços atuais.
    Filtra para incluir apenas símbolos de interesse e ignora BRL/outros.
    """
    account_info = binance_api.get_account_info()
    portfolio = {}
    usdt_balance = 0.0

    if account_info:
        # Pega saldos de ativos da conta
        for balance in account_info['balances']:
            asset = balance['asset']
            free = float(balance['free'])
            locked = float(balance['locked'])
            total_amount = free + locked

            if total_amount > 0:
                # Se for USDT, adicione ao saldo de caixa
                if asset == "USDT":
                    usdt_balance = total_amount
                    portfolio["USDT"] = {"amount": usdt_balance, "current_price": 1.0} # Preço do USDT é 1.0
                else:
                    # Verifica se o ativo é um dos símbolos que queremos monitorar (ex: BTC, ETH)
                    # e se forma um par válido com USDT (ex: BTCUSDT)
                    symbol_pair = asset + "USDT"
                    if symbol_pair in symbols_to_watch: # Verifica se é um dos pares monitorados
                        current_price = binance_api.get_current_price(symbol_pair)
                        if current_price is not None:
                            portfolio[symbol_pair] = {
                                "amount": total_amount,
                                "current_price": current_price,
                                "free": free,
                                "locked": locked
                            }
                        else:
                            print(f"Aviso: Não foi possível obter o preço para {symbol_pair}. Ignorando este ativo no portfólio.")
    return usdt_balance, portfolio

def generate_openai_prompt(usdt_balance, portfolio_data):
    """Gera um prompt detalhado para o OpenAI com base no portfólio atual."""
    prompt = "Seu portfólio atual é: "
    for symbol, data in portfolio_data.items():
        if symbol == "USDT":
            prompt += f"{data['amount']:.4f} USDT (cash), "
        else:
            prompt += f"{data['amount']:.4f} {symbol.replace('USDT', '')} (current price: ${data['current_price']:.4f}), "
    
    # Remove a vírgula extra no final se houver
    prompt = prompt.rstrip(', ') + ". "

    prompt += f"Você tem {usdt_balance:.2f} USDT disponíveis para negociar. "
    prompt += "Seu objetivo é maximizar os lucros em um mercado de criptomoedas volátil. "
    prompt += "Analise o mercado atual com base nas informações do seu portfólio. "
    prompt += "Você deve retornar APENAS uma ação de negociação no formato JSON, como uma lista de objetos. "
    prompt += "Se nenhuma ação for necessária, retorne uma lista vazia `[]`. "
    prompt += "As ações disponíveis são 'BUY' ou 'SELL'. "
    prompt += "Para 'BUY', inclua 'symbol' (ex: 'BTCUSDT') e 'usdt_amount' (valor em USDT para gastar). "
    prompt += "Para 'SELL', inclua 'symbol' (ex: 'BTCUSDT') e 'quantity' (quantidade da criptomoeda para vender). "
    prompt += f"A quantidade máxima de USDT que você pode gastar em uma única compra é {global_config['QUANTITY_PER_TRADE_USDT']}. "
    prompt += "Não tente comprar ou vender USDT diretamente. "
    prompt += "Exemplos de formato de saída:\n"
    prompt += "Para comprar: `[{\"action\": \"BUY\", \"symbol\": \"BTCUSDT\", \"usdt_amount\": 10}]`\n"
    prompt += "Para vender: `[{\"action\": \"SELL\", \"symbol\": \"ETHUSDT\", \"quantity\": 0.05}]`\n"
    prompt += "Para manter: `[]`"
    return prompt

def parse_openai_response(response_str):
    """
    Analisa a string de resposta do OpenAI, extraindo o JSON.
    Lida com o encapsulamento de Markdown (```json ... ```).
    """
    # Remove o encapsulamento de markdown se presente
    clean_response = response_str.replace("```json", "").replace("```", "").strip()
    
    try:
        # Tenta carregar o JSON
        actions = json.loads(clean_response)
        if not isinstance(actions, list):
            print(f"Aviso: Resposta do OpenAI não é uma lista. Recebido: {actions}")
            return []
        return actions
    except json.JSONDecodeError as e:
        print(f"Erro ao analisar JSON da resposta do OpenAI: {e}. Resposta: {response_str}")
        return []
    except Exception as e:
        print(f"Erro inesperado ao processar resposta do OpenAI: {e}. Resposta: {response_str}")
        return []

def execute_trade_action(action, binance_api, current_prices, usdt_balance, user_config):
    """Executa a ação de compra ou venda recomendada pelo OpenAI."""
    action_type = action.get('action')
    symbol = action.get('symbol')

    if action_type == 'BUY':
        usdt_amount = action.get('usdt_amount')
        if not symbol or not usdt_amount or usdt_amount <= 0:
            print(f"Ação de compra inválida: {action}. Ignorando.")
            return

        if usdt_amount > usdt_balance:
            print(f"Não há USDT suficiente para comprar {usdt_amount} USDT de {symbol}. Saldo disponível: {usdt_balance:.2f} USDT. Ignorando compra.")
            return
        
        # Limita a quantidade de compra por trade
        max_trade_usdt = user_config.get('QUANTITY_PER_TRADE_USDT', 10)
        if usdt_amount > max_trade_usdt:
            print(f"Aviso: Quantidade de compra ({usdt_amount} USDT) excede o limite por trade ({max_trade_usdt} USDT). Ajustando para {max_trade_usdt} USDT.")
            usdt_amount = max_trade_usdt

        current_price = current_prices.get(symbol)
        if not current_price:
            print(f"Não foi possível obter o preço atual para {symbol}. Não é possível comprar.")
            return

        # Calcula a quantidade a ser comprada
        quantity = usdt_amount / current_price
        # A Binance tem requisitos de "step size" para a quantidade.
        # Para simplificar aqui, vamos arredondar para um número razoável de casas decimais.
        # Em produção, usaria client.get_symbol_info(symbol) para obter filtros de quantidade.
        # Ex: arredondar para 5 casas decimais para a maioria das altcoins.
        quantity = round(quantity, 5) # Ajuste conforme a precisão do ativo

        if quantity <= 0:
            print(f"Quantidade calculada para compra de {symbol} é zero ou negativa. Ignorando.")
            return
            
        print(f"Executando compra de {quantity} {symbol} com {usdt_amount} USDT.")
        order = binance_api.buy_market(symbol, quantity)
        if order:
            print(f"Compra de {symbol} executada com sucesso. ID da Ordem: {order.get('orderId')}")
            return {"type": "BUY", "symbol": symbol, "executed_quantity": order.get('executedQty'), "price": order.get('fills')[0].get('price') if order.get('fills') else 'N/A'}
        else:
            print(f"Falha na compra de {symbol}.")

    elif action_type == 'SELL':
        quantity_to_sell = action.get('quantity')
        if not symbol or not quantity_to_sell or quantity_to_sell <= 0:
            print(f"Ação de venda inválida: {action}. Ignorando.")
            return

        # Verifique se o ativo existe no portfólio e se há quantidade suficiente
        # Note: 'portfolio_data' vem no 'user_config' passado para esta função.
        current_holdings = user_config.get('portfolio_data', {}).get(symbol, {}).get('amount', 0)
        if quantity_to_sell > current_holdings:
            print(f"Não há {quantity_to_sell} {symbol} para vender. Saldo disponível: {current_holdings:.4f} {symbol}. Ignorando venda.")
            return
        
        print(f"Executando venda de {quantity_to_sell} {symbol}.")
        order = binance_api.sell_market(symbol, quantity_to_sell)
        if order:
            print(f"Venda de {symbol} executada com sucesso. ID da Ordem: {order.get('orderId')}")
            return {"type": "SELL", "symbol": symbol, "executed_quantity": order.get('executedQty'), "price": order.get('fills')[0].get('price') if order.get('fills') else 'N/A'}
        else:
            print(f"Falha na venda de {symbol}.")
    else:
        print(f"Tipo de ação desconhecido: {action_type}. Ignorando.")
    return None

# ATUALIZADO: A função run_bot agora aceita um dicionário de configuração completo
# que inclui a chave da OpenAI, e também 'app_dashboard_data' para acesso direto.
def run_bot(user_id, api_key, secret_key, config, stop_event, app_dashboard_data):
    """
    Função principal do bot que é executada em uma thread.
    Recebe user_id, api_key, secret_key e um dicionário 'config' que contém a chave OpenAI,
    e outras configurações globais. 'app_dashboard_data' é uma referência ao dicionário
    de dados do dashboard no app.py.
    """
    global global_config
    global_config = config # Salva a configuração passada, incluindo a chave OpenAI

    binance_api = BinanceAPI(api_key, secret_key)
    
    # Agora a chave da OpenAI vem dentro do dicionário 'config'
    openai_api = OpenAIAPI(global_config.get("OPENAI_API_KEY"))

    trade_interval = global_config.get("TRADE_INTERVAL_SECONDS", 300)
    max_trades_per_cycle = global_config.get("MAX_TRADES_PER_CYCLE", 1)
    
    # Lista de símbolos a serem observados (pode vir de config.json via global_config)
    symbols_to_watch = global_config.get('symbols_to_watch', ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT", "ADAUSDT", "FETUSDT", "AVAXUSDT", "OMUSDT", "RNDRUSDT", "TRUMPUSDT"])

    print(f"\n--- Bot para usuário {user_id} iniciado ---")
    print(f"Intervalo de negociação: {trade_interval} segundos")

    while not stop_event.is_set():
        current_time = int(time.time())
        next_cycle_time = current_time + trade_interval
        
        # ATUALIZADO: Passa user_id para send_to_dashboard
        send_to_dashboard(user_id, {"next_cycle_time": next_cycle_time})

        print(f"\nExecutando ciclo de negociação para o usuário {user_id} às {datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. Obter saldo e portfólio do Binance
        usdt_balance, portfolio_data = get_binance_balance_and_portfolio(binance_api, symbols_to_watch)
        
        # Adiciona USDT ao portfolio_data para que o prompt da IA o inclua
        # E também garante que o dashboard tenha o USDT correto
        portfolio_data["USDT"] = {"amount": usdt_balance, "current_price": 1.0}

        # Atualiza o dashboard com os dados atuais do portfólio e saldo
        # ATUALIZADO: Passa user_id para send_to_dashboard
        send_to_dashboard(user_id, {
            "status": "Analisando portfólio...",
            "usdt": usdt_balance,
            "portfolio": portfolio_data
        })

        # 2. Gerar prompt para OpenAI
        prompt = generate_openai_prompt(usdt_balance, portfolio_data)
        print(f"[OpenAI Prompt]: {prompt}")

        # 3. Obter recomendação do OpenAI
        openai_response_str = openai_api.get_completion(prompt)
        print(f"[OpenAI Response]: {openai_response_str}")
        
        trade_actions = parse_openai_response(openai_response_str)

        if trade_actions:
            print(f"OpenAI recomendou {len(trade_actions)} ações.")
            executed_trades_count = 0
            history_updates = []

            # Para cada ação recomendada, execute-a
            for action in trade_actions:
                if executed_trades_count >= max_trades_per_cycle:
                    print(f"Limite de {max_trades_per_cycle} negociações por ciclo atingido. Ignorando ações restantes.")
                    break
                
                # ATUALIZADO: Passa user_id para send_to_dashboard
                send_to_dashboard(user_id, {"status": f"Executando ação: {action.get('action')} {action.get('symbol')}"})
                
                # Obter preços atualizados para todas as moedas monitoradas antes de executar a ação
                current_prices = {}
                for symbol_pair in symbols_to_watch:
                    price = binance_api.get_current_price(symbol_pair)
                    if price:
                        current_prices[symbol_pair] = price

                # Passa a configuração do usuário e o portfolio_data para execute_trade_action
                user_config_for_trade = global_config.copy()
                user_config_for_trade["portfolio_data"] = portfolio_data
                
                trade_result = execute_trade_action(action, binance_api, current_prices, usdt_balance, user_config_for_trade)
                
                if trade_result:
                    executed_trades_count += 1
                    # Atualiza o histórico para o dashboard
                    history_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "type": trade_result["type"],
                        "symbol": trade_result["symbol"],
                        "quantity": trade_result["executed_quantity"],
                        "price": trade_result["price"]
                    }
                    history_updates.append(history_entry)
                    print(f"Negociação registrada: {history_entry}")

            if history_updates:
                # ATUALIZADO: Passa user_id para send_to_dashboard
                send_to_dashboard(user_id, {"history": history_updates, "status": "Negociações executadas. Atualizando portfólio..."})
            else:
                # ATUALIZADO: Passa user_id para send_to_dashboard
                send_to_dashboard(user_id, {"status": "Nenhuma negociação executada neste ciclo."})
        else:
            print("Nenhuma ação recomendada pelo OpenAI. Mantendo portfólio.")
            # ATUALIZADO: Passa user_id para send_to_dashboard
            send_to_dashboard(user_id, {"status": "Nenhuma ação recomendada. Aguardando próximo ciclo."})
        
        print(f"Próximo ciclo de negociação para o usuário {user_id} em {trade_interval} segundos...")
        stop_event.wait(trade_interval) # Espera, mas permite que o bot seja parado