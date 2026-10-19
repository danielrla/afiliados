"""Cliente mínimo da Shopee Affiliate Open API (GraphQL), apenas stdlib."""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://open-api.affiliate.shopee.com.br/graphql"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class ShopeeAffiliateClient:
    def __init__(self, app_id: str | None = None, secret: str | None = None):
        load_env()
        self.app_id = app_id or os.environ.get("SHOPEE_AFFILIATE_APP_ID")
        self.secret = secret or os.environ.get("SHOPEE_AFFILIATE_SECRET")
        if not self.app_id or not self.secret:
            raise RuntimeError("SHOPEE_AFFILIATE_APP_ID/SHOPEE_AFFILIATE_SECRET ausentes no .env")

    def _auth_header(self, payload: str) -> str:
        ts = str(int(time.time()))
        signature = hashlib.sha256(f"{self.app_id}{ts}{payload}{self.secret}".encode()).hexdigest()
        return f"SHA256 Credential={self.app_id},Timestamp={ts},Signature={signature}"

    def execute(self, query: str, variables: dict | None = None) -> dict:
        body = {"query": query}
        if variables:
            body["variables"] = variables
        # Serialização canônica: o mesmo texto é assinado e enviado.
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

    def get_product_image_url(self, item_id: str | int) -> str | None:
        """Busca a URL oficial da imagem de alta resolução do produto via GraphQL productOfferV2."""
        try:
            clean_id = int(str(item_id).strip())
        except (ValueError, TypeError):
            return None

        query = f"""query{{productOfferV2(itemId:{clean_id}){{nodes{{itemId imageUrl productName price offerLink}}pageInfo{{page limit hasNextPage}}}}}}"""
        try:
            resp = self.execute(query)
            nodes = resp.get("data", {}).get("productOfferV2", {}).get("nodes", [])
            if nodes and nodes[0].get("imageUrl"):
                return nodes[0]["imageUrl"]
        except Exception as e:
            print(f"Aviso ao consultar imagem na Shopee API para item {item_id}: {e}")
        return None



TEST_QUERY = """query{productOfferV2(listType:0,sortType:2,page:1,limit:2){nodes{itemId productName price commissionRate offerLink}pageInfo{page limit hasNextPage}}}"""


if __name__ == "__main__":
    result = ShopeeAffiliateClient().execute(TEST_QUERY)
    print(json.dumps(result, indent=2, ensure_ascii=False))
