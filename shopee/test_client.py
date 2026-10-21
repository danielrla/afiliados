"""Testes unitários e de integração para ShopeeAffiliateClient e DTOs."""
import unittest
from shopee.client import (
    ShopeeAffiliateClient,
    ShopeeOfferItem,
    ShopeeOfferSearchResult,
    ShopeeConversionItem,
)


class TestShopeeClient(unittest.TestCase):
    def test_sanitizar_sub_id(self):
        """Valida que subIds são higienizados para o padrão alfanumérico aceito pela Shopee."""
        self.assertEqual(ShopeeAffiliateClient.sanitizar_sub_id("wa_grupo"), "wagrupo")
        self.assertEqual(ShopeeAffiliateClient.sanitizar_sub_id("FACEBOOK-FEED!"), "facebookfeed")
        self.assertEqual(ShopeeAffiliateClient.sanitizar_sub_id(""), "")
        long_id = "a" * 30
        self.assertEqual(len(ShopeeAffiliateClient.sanitizar_sub_id(long_id)), 20)

    def test_dto_offer_item_serialization(self):
        """Valida a serialização para dicionário do DTO ShopeeOfferItem."""
        item = ShopeeOfferItem(
            item_id=12345,
            product_name="Produto Teste",
            price="99.90",
            commission_rate="0.10",
            commission="9.99",
            sales=150,
            rating_star=4.8,
            image_url="https://cf.shopee.com.br/file/exemplo.jpg",
            product_link="https://shopee.com.br/produto",
            offer_link="https://s.shopee.com.br/teste",
            shop_name="Loja Parceira",
            shop_id=9876,
        )
        data = item.to_dict()
        self.assertEqual(data["item_id"], 12345)
        self.assertEqual(data["product_name"], "Produto Teste")
        self.assertEqual(data["sales"], 150)
        self.assertEqual(data["rating_star"], 4.8)

    def test_dto_search_result_serialization(self):
        """Valida a estrutura de retorno paginado do DTO ShopeeOfferSearchResult."""
        res = ShopeeOfferSearchResult(
            items=[],
            page=2,
            limit=10,
            has_next_page=True,
        )
        data = res.to_dict()
        self.assertEqual(data["page"], 2)
        self.assertEqual(data["limit"], 10)
        self.assertTrue(data["has_next_page"])
        self.assertEqual(data["items"], [])

    def test_auth_header_format(self):
        """Valida que o formato do cabeçalho SHA256 segue estritamente a especificação da Shopee."""
        client = ShopeeAffiliateClient(app_id="123456", secret="secret_teste")
        header = client._auth_header('{"query":"{}"}')
        self.assertTrue(header.startswith("SHA256 Credential=123456,Timestamp="))
        self.assertIn(",Signature=", header)


if __name__ == "__main__":
    unittest.main()
