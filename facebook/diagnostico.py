"""Script utilitário para validação de escopos e descoberta da conta Instagram vinculada."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shopee.client import load_env
from facebook.client import FacebookPageClient


def executar_diagnostico():
    load_env()
    try:
        client = FacebookPageClient()
    except Exception as e:
        print(f"Erro ao inicializar FacebookPageClient: {e}")
        return

    print("=== Diagnóstico do Token Meta ===")
    try:
        token_info = client.debug_token()
        print(f"Token Válido: {token_info.get('is_valid')}")
        print(f"Tipo do Token: {token_info.get('type')}")
        print(f"App ID: {token_info.get('app_id')}")
        print(f"Profile ID: {token_info.get('profile_id')}")
        print(f"Expira em: {token_info.get('expires_at')}")
        print(f"Escopos concedidos: {token_info.get('scopes')}")
    except Exception as e:
        print(f"Falha ao validar token (debug_token): {e}")

    print("\n=== Dados da Página Facebook e Vínculo com Instagram ===")
    try:
        page_data = client._request("GET", client.page_id, {
            "fields": "id,name,instagram_business_account",
            "access_token": client.page_token,
        })
        print(f"ID da Página: {page_data.get('id')}")
        print(f"Nome da Página: {page_data.get('name')}")
        ig_account = page_data.get("instagram_business_account")
        if ig_account:
            print(f"[SUCESSO] Conta Instagram Business encontrada: ID {ig_account.get('id')}")
        else:
            print("[ALERTA] Nenhuma conta Instagram Business vinculada a esta Página do Facebook.")
            print("Verifique se a conta do Instagram foi convertida em Profissional e conectada nas configurações da Página no Meta Business Suite.")
    except Exception as e:
        print(f"Falha ao consultar metadados da Página: {e}")


if __name__ == "__main__":
    executar_diagnostico()
