"""Testes unitários para o módulo facebook e canais de controle."""
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import sqlite3

from db.controle import (
    CANAIS_OBRIGATORIOS,
    inicializar_banco,
    registrar_produto,
    registrar_resultado_canal,
    obter_status_canais,
    obter_produto,
)
from shopee.client import ShopeeAffiliateClient


class TestFacebookReels(unittest.TestCase):
    def test_canais_obrigatorios_contem_facebook_reels(self):
        """Garante que facebook_reels está registrado na lista de canais gerenciados."""
        self.assertIn("facebook_reels", CANAIS_OBRIGATORIOS)
        self.assertEqual(len(CANAIS_OBRIGATORIOS), 6)

    def test_shopee_sub_id_facebook_reels(self):
        """Garante que a Shopee sanitiza corretamente o canal facebook_reels."""
        sub_id = ShopeeAffiliateClient.sanitizar_sub_id("facebook_reels")
        self.assertEqual(sub_id, "facebookreels")

    def test_fluxo_status_com_facebook_reels(self):
        """Valida que o registro e conclusão dos 6 canais resulta em status CONCLUIDO."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_db = Path(tmpdir) / "test_publicacoes.db"
            inicializar_banco(test_db)

            prod = {
                "item_id": "999888777",
                "item_name": "Produto Teste Reels",
                "offer_link": "https://s.shopee.com.br/teste",
            }
            inserido = registrar_produto(prod, db_path=test_db)
            self.assertTrue(inserido)

            # Registra sucesso em todos os 6 canais
            for canal in CANAIS_OBRIGATORIOS:
                registrar_resultado_canal(
                    "999888777",
                    canal,
                    "SUCESSO",
                    id_externo=f"ext_{canal}",
                    db_path=test_db,
                )

            status = obter_status_canais("999888777", db_path=test_db)
            self.assertEqual(status.get("facebook_reels"), "SUCESSO")

            produto_final = obter_produto("999888777", db_path=test_db)
            self.assertEqual(produto_final["status_geral"], "CONCLUIDO")


if __name__ == "__main__":
    unittest.main()
