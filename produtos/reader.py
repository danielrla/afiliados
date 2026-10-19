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


def fetch_product_images(product_link: str, max_images: int = 5) -> list[str]:
    """Busca as imagens de alta resolução do produto a partir da URL da Shopee."""
    req = urllib.request.Request(product_link, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", "ignore")
    except (urllib.error.URLError, TimeoutError) as e:
        html = ""
        try:
            import subprocess
            cmd = ["curl", "-sL", "-A", USER_AGENT, product_link]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                html = res.stdout
        except Exception:
            pass
        if not html:
            print(f"Erro ao carregar {product_link}: {e}")
            return []

    images: list[str] = []

    # 1. Imagem principal via Open Graph
    og_match = re.search(r'content=[\"\']([^\"\']+)[\"\']\s+property=[\"\']og:image[\"\']', html) or \
               re.search(r'property=[\"\']og:image[\"\']\s+content=[\"\']([^\"\']+)[\"\']', html)
    if og_match:
        images.append(og_match.group(1))

    # 2. Imagens adicionais da galeria (CDN nacional e internacional da Shopee)
    pattern_ids = re.findall(r'(?:br|sg|my|id|ph|th|vn)-[0-9]+-[a-z0-9-]+', html)
    seen = {img.split("/")[-1] for img in images}
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
