"""Leitor de produtos Shopee a partir de arquivos CSV e extrator de imagens via Product Link."""
import csv
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "produtos" / "001.csv"
USER_AGENT = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"


def _find_chrome_bin() -> str | None:
    """Localiza o binário do Chrome ou Chromium no sistema operacional."""
    import os
    candidatos = [
        os.environ.get("CHROME_PATH"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for c in candidatos:
        if c and Path(c).exists():
            return c
    return None


def fetch_product_images(product_link: str, max_images: int = 5, item_id: str | None = None) -> list[str]:
    """Busca as imagens de alta resolução do produto a partir da URL da Shopee via Chrome headless, API oficial ou scraping."""
    import subprocess
    images: list[str] = []

    # 1. Tentativa via Shopee Affiliate Open API se o item_id estiver disponível
    clean_id = item_id
    if not clean_id and product_link:
        m = re.search(r'/(\d{8,})(?:\?|$)', product_link)
        if m:
            clean_id = m.group(1)

    if clean_id:
        try:
            from shopee.client import ShopeeAffiliateClient
            api_client = ShopeeAffiliateClient()
            if hasattr(api_client, "get_product_image_url"):
                api_img = api_client.get_product_image_url(clean_id)
                if api_img:
                    images.append(api_img)
        except Exception:
            pass

    # 2. Extração via Chrome / Chromium Headless (executa o JavaScript da Shopee SPA)
    chrome_bin = _find_chrome_bin()
    html = ""
    if chrome_bin and product_link:
        try:
            cmd = [
                chrome_bin,
                "--headless=new",
                "--dump-dom",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
                product_link,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0 and res.stdout:
                html = res.stdout
        except Exception as e:
            print(f"Aviso: falha ao extrair DOM via Chrome headless: {e}")

    # 3. Fallback via requisição HTTP direta com cabeçalhos de navegador real
    if not html and product_link:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://shopee.com.br/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        }
        try:
            req = urllib.request.Request(product_link, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", "ignore")
        except Exception:
            try:
                cmd = ["curl", "-sL", "-A", headers["User-Agent"], "-e", headers["Referer"], product_link]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
                if res.returncode == 0:
                    html = res.stdout
            except Exception:
                html = ""

    # 4. Extração da imagem principal via Open Graph
    if html:
        og_match = re.search(r'property=[\"\']og:image[\"\']\s+content=[\"\']([^\"\']+)[\"\']', html) or \
                   re.search(r'content=[\"\']([^\"\']+)[\"\']\s+property=[\"\']og:image[\"\']', html)
        if og_match:
            og_url = og_match.group(1).strip()
            # Limpa parâmetros de redimensionamento e extensões adicionais
            og_clean = re.sub(r'(@resize.*|\.webp)$', '', og_url)
            if og_clean not in images:
                images.append(og_clean)

        # 5. Imagens adicionais da galeria na CDN da Shopee
        pattern_ids = re.findall(r'(?:br|sg|my|id|ph|th|vn)-[0-9]+-[a-z0-9-]+', html)
        seen = {img.split("/")[-1].split(".")[0].split("@")[0] for img in images}
        for img_id in pattern_ids:
            if img_id not in seen:
                seen.add(img_id)
                images.append(f"https://down-br.img.susercontent.com/file/{img_id}")
                if len(images) >= max_images:
                    break

    return images


def load_products_from_csv(file_path: Path = CSV_PATH, limit: int | None = None) -> list[dict]:
    """Lê os produtos do arquivo CSV e enriquece com as imagens encontradas."""
    products = []
    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

    with file_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=",")
        for i, row in enumerate(reader):
            if limit and i >= limit:
                break

            item_name = row.get("Item Name", "").strip()
            offer_link = row.get("Offer Link", "").strip()
            product_link = row.get("Product Link", "").strip()
            price = row.get("Price", "").strip()
            commission = row.get("Commission", "").strip()

            images = fetch_product_images(product_link, max_images=4) if product_link else []

            products.append({
                "item_name": item_name,
                "offer_link": offer_link,
                "product_link": product_link,
                "price": price,
                "commission": commission,
                "images": images,
            })

    return products


if __name__ == "__main__":
    records = load_products_from_csv(limit=5)
    print(json.dumps(records, indent=2, ensure_ascii=False))
