# chatgpt_api.py
from openai import OpenAI
import json

class OpenAIAPI:
    def __init__(self, api_key):
        """
        Inicializa o cliente OpenAI com a chave da API fornecida.
        """
        self.client = OpenAI(api_key=api_key)

    def get_completion(self, prompt, model="gpt-4o", temperature=0):
        """
        Envia um prompt para a API do OpenAI e retorna a conclusão.
        """
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Erro ao obter resposta do OpenAI: {e}")
            return "Manter portfolio atual." # Resposta de fallback em caso de erro