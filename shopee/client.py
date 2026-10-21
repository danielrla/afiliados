"""Cliente da Shopee Affiliate Open API (GraphQL) e DTOs de negócio.

Este módulo encapsula as operações criptográficas de autenticação SHA-256 e o transporte
de dados com o endpoint GraphQL oficial da Shopee Brasil, fornecendo contratos tipados
(DTOs) para busca de ofertas, encurtamento dinâmico de links e reconciliação de vendas.
"""
from dataclasses import dataclass, field, asdict
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

ENDPOINT = "https://open-api.affiliate.shopee.com.br/graphql"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = ENV_PATH) -> None:
    """Carrega variáveis de ambiente a partir de arquivo .env sem expor valores confidenciais."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class ShopeeOfferItem:
    """Contrato de dados para uma oferta ou produto obtido via Shopee Affiliate API."""
    item_id: int
    product_name: str
    price: str
    commission_rate: str
    commission: str
    sales: int
    rating_star: float
    image_url: str
    product_link: str
    offer_link: str
    shop_name: str
    shop_id: int
    period_start_time: Optional[int] = None
    period_end_time: Optional[int] = None

    def to_dict(self) -> dict:
        """Converte a entidade para dicionário serializável."""
        return asdict(self)


@dataclass
class ShopeeOfferSearchResult:
    """Resultado paginado de consulta ao catálogo de ofertas da Shopee."""
    items: list[ShopeeOfferItem] = field(default_factory=list)
    page: int = 1
    limit: int = 20
    has_next_page: bool = False

    def to_dict(self) -> dict:
        """Converte o resultado completo para dicionário."""
        return {
            "items": [item.to_dict() for item in self.items],
            "page": self.page,
            "limit": self.limit,
            "has_next_page": self.has_next_page,
        }


@dataclass
class ShopeeConversionItem:
    """Representação de um item de pedido faturado para reconciliação financeira."""
    conversion_id: str
    order_id: str
    item_id: int
    item_name: str
    item_price: str
    item_commission: str
    order_status: str
    purchase_time: str
    channel_type: Optional[str] = None
    sub_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Converte o registro para dicionário serializável."""
        return asdict(self)


class ShopeeAffiliateClient:
    """Cliente HTTP para autenticação e consumo da Shopee Affiliate Open API via GraphQL."""

    CANAL_SUBID_MAP = {
        "whatsapp": "wagrupo",
        "facebook": "fbfeed",
        "instagram_stories": "igstories",
        "instagram_post": "igpost",
        "instagram_reels": "igreels",
    }

    def __init__(self, app_id: str | None = None, secret: str | None = None):
        load_env()
        self.app_id = app_id or os.environ.get("SHOPEE_AFFILIATE_APP_ID")
        self.secret = secret or os.environ.get("SHOPEE_AFFILIATE_SECRET")
        if not self.app_id or not self.secret:
            raise RuntimeError("SHOPEE_AFFILIATE_APP_ID/SHOPEE_AFFILIATE_SECRET ausentes no .env")

    def _auth_header(self, payload: str) -> str:
        """Gera o cabeçalho SHA-256 com base em AppId, Timestamp, Payload e Secret."""
        ts = str(int(time.time()))
        signature = hashlib.sha256(f"{self.app_id}{ts}{payload}{self.secret}".encode()).hexdigest()
        return f"SHA256 Credential={self.app_id},Timestamp={ts},Signature={signature}"

    def execute(self, query: str, variables: dict | None = None) -> dict:
        """Executa requisição HTTP POST GraphQL com serialização canônica e assinatura."""
        body = {"query": query}
        if variables:
            body["variables"] = variables
        payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        req = urllib.request.Request(
            ENDPOINT,
            data=payload.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": self._auth_header(payload),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}") from e

    @staticmethod
    def sanitizar_sub_id(sub_id: str) -> str:
        """Sanitiza o subId para conter unicamente caracteres alfanuméricos minúsculos (máx 20 chars)."""
        limpo = re.sub(r"[^a-zA-Z0-9]", "", str(sub_id).strip().lower())
        return limpo[:20]

    def gerar_link_rastreado(self, origin_url: str, sub_ids: list[str]) -> str | None:
        """Gera um link de afiliado encurtado injetando subIds alfanuméricos para rastreio."""
        if not origin_url:
            return None

        sub_ids_sanitizados = [self.sanitizar_sub_id(s) for s in sub_ids if s]
        sub_ids_sanitizados = [s for s in sub_ids_sanitizados if s]

        mutation = """mutation GenerateShortLink($input: ShortLinkInput!) {
            generateShortLink(input: $input) {
                shortLink
            }
        }"""
        variables = {
            "input": {
                "originUrl": origin_url,
                "subIds": sub_ids_sanitizados,
            }
        }

        try:
            resp = self.execute(mutation, variables)
            data = resp.get("data", {})
            if data and data.get("generateShortLink"):
                return data["generateShortLink"].get("shortLink")
            if resp.get("errors"):
                print(f"Aviso ao gerar shortLink na Shopee: {resp['errors']}")
        except Exception as e:
            print(f"Erro ao gerar shortLink para {origin_url}: {e}")
        return None

    def gerar_link_canal(self, origin_url: str, canal: str, identificador_extra: str | None = None) -> str | None:
        """Gera link de afiliado com subId específico de canal para atribuição precisa."""
        sub_id_canal = self.CANAL_SUBID_MAP.get(canal, self.sanitizar_sub_id(canal))
        sub_ids = [sub_id_canal]
        if identificador_extra:
            sub_ids.append(self.sanitizar_sub_id(identificador_extra))
        return self.gerar_link_rastreado(origin_url, sub_ids)

    def buscar_ofertas(
        self,
        keyword: str | None = None,
        sort_type: int = 2,
        page: int = 1,
        limit: int = 20,
        item_id: int | None = None,
        list_type: int = 0,
    ) -> ShopeeOfferSearchResult:
        """
        Consulta produtos elegíveis a comissão via query GraphQL productOfferV2.
        list_type: 0 (todos/geral).
        sort_type: 1 (relevância), 2 (top vendas), 5 (maior comissão).
        """
        args = [f"listType: {list_type}", f"sortType: {sort_type}", f"page: {page}", f"limit: {limit}"]
        if keyword:
            safe_kw = json.dumps(str(keyword))
            args.append(f"keyword: {safe_kw}")
        if item_id:
            args.append(f"itemId: {int(item_id)}")

        args_str = ", ".join(args)
        query = f"""query {{
            productOfferV2({args_str}) {{
                nodes {{
                    itemId
                    productName
                    price
                    commissionRate
                    commission
                    sales
                    ratingStar
                    imageUrl
                    productLink
                    offerLink
                    shopName
                    shopId
                    periodStartTime
                    periodEndTime
                }}
                pageInfo {{
                    page
                    limit
                    hasNextPage
                }}
            }}
        }}"""

        resp = self.execute(query)
        data = resp.get("data", {}).get("productOfferV2", {})
        nodes = data.get("nodes", [])
        page_info = data.get("pageInfo", {})

        itens: list[ShopeeOfferItem] = []
        for n in nodes:
            itens.append(
                ShopeeOfferItem(
                    item_id=n.get("itemId", 0),
                    product_name=n.get("productName", ""),
                    price=str(n.get("price", "0")),
                    commission_rate=str(n.get("commissionRate", "0")),
                    commission=str(n.get("commission", "0")),
                    sales=int(n.get("sales") or 0),
                    rating_star=float(n.get("ratingStar") or 0.0),
                    image_url=n.get("imageUrl", ""),
                    product_link=n.get("productLink", ""),
                    offer_link=n.get("offerLink", ""),
                    shop_name=n.get("shopName", ""),
                    shop_id=int(n.get("shopId") or 0),
                    period_start_time=n.get("periodStartTime"),
                    period_end_time=n.get("periodEndTime"),
                )
            )

        return ShopeeOfferSearchResult(
            items=itens,
            page=page_info.get("page", page),
            limit=page_info.get("limit", limit),
            has_next_page=bool(page_info.get("hasNextPage", False)),
        )

    def get_product_image_url(self, item_id: str | int) -> str | None:
        """Busca a URL oficial da imagem de alta resolução do produto via GraphQL productOfferV2."""
        try:
            clean_id = int(str(item_id).strip())
        except (ValueError, TypeError):
            return None

        try:
            resultado = self.buscar_ofertas(limit=1, item_id=clean_id)
            if resultado.items and resultado.items[0].image_url:
                return resultado.items[0].image_url
        except Exception as e:
            print(f"Aviso ao consultar imagem na Shopee API para item {item_id}: {e}")
        return None

    def obter_relatorio_conversoes(
        self,
        purchase_time_start: int | None = None,
        purchase_time_end: int | None = None,
        limit: int = 50,
        scroll_id: str | None = None,
    ) -> list[ShopeeConversionItem]:
        """Consulta relatório de conversões e pedidos faturados com detalhamento de itens."""
        args = [f"limit: {limit}"]
        if purchase_time_start:
            args.append(f"purchaseTimeStart: {int(purchase_time_start)}")
        if purchase_time_end:
            args.append(f"purchaseTimeEnd: {int(purchase_time_end)}")
        if scroll_id:
            safe_scroll = json.dumps(str(scroll_id))
            args.append(f"scrollId: {safe_scroll}")

        args_str = ", ".join(args)
        query = f"""query {{
            conversionReport({args_str}) {{
                nodes {{
                    conversionId
                    purchaseTime
                    conversionStatus
                    grossCommission
                    totalCommission
                    netCommission
                    orders {{
                        orderId
                        orderStatus
                        items {{
                            itemId
                            itemName
                            itemPrice
                            itemCommission
                            itemTotalCommission
                            channelType
                        }}
                    }}
                }}
                pageInfo {{
                    limit
                    hasNextPage
                    scrollId
                }}
            }}
        }}"""

        try:
            resp = self.execute(query)
            nodes = resp.get("data", {}).get("conversionReport", {}).get("nodes", [])
            conversoes: list[ShopeeConversionItem] = []
            for n in nodes:
                conv_id = str(n.get("conversionId", ""))
                p_time = str(n.get("purchaseTime", ""))
                for ord_entry in n.get("orders", []):
                    o_id = str(ord_entry.get("orderId", ""))
                    o_status = str(ord_entry.get("orderStatus", ""))
                    for item in ord_entry.get("items", []):
                        conversoes.append(
                            ShopeeConversionItem(
                                conversion_id=conv_id,
                                order_id=o_id,
                                item_id=int(item.get("itemId") or 0),
                                item_name=str(item.get("itemName", "")),
                                item_price=str(item.get("itemPrice", "0")),
                                item_commission=str(item.get("itemTotalCommission") or item.get("itemCommission") or "0"),
                                order_status=o_status,
                                purchase_time=p_time,
                                channel_type=item.get("channelType"),
                            )
                        )
            return conversoes
        except Exception as e:
            print(f"Erro ao consultar relatório de conversões: {e}")
            return []


if __name__ == "__main__":
    client = ShopeeAffiliateClient()
    ofertas = client.buscar_ofertas(limit=2)
    print(json.dumps(ofertas.to_dict(), indent=2, ensure_ascii=False))
