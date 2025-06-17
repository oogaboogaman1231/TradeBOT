# binance_api.py
from binance.client import Client
from binance.exceptions import BinanceAPIException # Importe para tratar erros específicos
import json
import requests # Mantenha se você tiver outras funcionalidades HTTP

class BinanceAPI:
    def __init__(self, api_key, api_secret):
        self.client = Client(api_key, api_secret)

    def get_account_info(self):
        """Retorna informações da conta."""
        try:
            return self.client.get_account()
        except BinanceAPIException as e:
            print(f"Erro da API Binance ao obter informações da conta: {e}")
            return None
        except Exception as e:
            print(f"Erro inesperado ao obter informações da conta: {e}")
            return None

    def get_current_price(self, symbol):
        """Obtém o preço atual de um símbolo."""
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except BinanceAPIException as e:
            print(f"Erro da API Binance ao obter preço para {symbol}: {e}")
            return None
        except Exception as e:
            print(f"Erro inesperado ao obter preço para {symbol}: {e}")
            return None

    def buy_market(self, symbol, quantity):
        """Executa uma ordem de compra a mercado."""
        try:
            # Em um ambiente real, você precisa validar quantity
            order = self.client.order_market_buy(
                symbol=symbol,
                quantity=quantity
            )
            print(f"Ordem de compra a mercado de {quantity} {symbol} executada: {order}")
            return order
        except BinanceAPIException as e:
            print(f"Erro da API Binance ao executar compra de {symbol}: {e}. Código: {e.code}, Mensagem: {e.message}")
            return None
        except Exception as e:
            print(f"Erro inesperado ao executar compra de {symbol}: {e}")
            return None

    def sell_market(self, symbol, quantity):
        """Executa uma ordem de venda a mercado."""
        try:
            # Em um ambiente real, você precisa validar quantity com minQty, stepSize etc.
            order = self.client.order_market_sell(
                symbol=symbol,
                quantity=quantity
            )
            print(f"Ordem de venda a mercado de {quantity} {symbol} executada: {order}")
            return order
        except BinanceAPIException as e:
            print(f"Erro da API Binance ao executar venda de {symbol}: {e}. Código: {e.code}, Mensagem: {e.message}")
            return None
        except Exception as e:
            print(f"Erro inesperado ao executar venda de {symbol}: {e}")
            return None
            
    # Pode manter get_price como um alias se preferir
    def get_price(self, symbol):
        return self.get_current_price(symbol)