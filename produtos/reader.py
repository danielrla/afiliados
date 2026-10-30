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


def extrair_produto_de_link(url: str) -> dict:
    """Extrai metadados (item_id, item_name, price, image_url, offer_link, product_link) a partir de qualquer link de produto/afiliado (Mercado Livre, Shopee, etc.)."""
    import hashlib
    import html as html_lib
    import subprocess

    raw_url = str(url or "").strip()
    if not raw_url:
        raise ValueError("URL do produto não informada.")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    final_url = raw_url
    html = ""

    # 1. Segue redirecionamentos e captura HTML + URL final via curl (suporta HTTP/2 e TLS moderno do meli.la / Shopee)
    try:
        res = subprocess.run(
            ["curl", "-sL", "--max-time", "15", "-w", "\n__FINAL_URL__:%{url_effective}", "-A", headers["User-Agent"], raw_url],
            capture_output=True,
            text=True,
            timeout=18,
        )
        if res.returncode == 0 and res.stdout:
            parts = res.stdout.rsplit("\n__FINAL_URL__:", 1)
            html = parts[0]
            if len(parts) > 1 and parts[1].strip():
                final_url = parts[1].strip()
    except Exception:
        pass

    # 2. Fallback via urllib caso curl não tenha retornado HTML
    if not html:
        try:
            req = urllib.request.Request(raw_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                final_url = resp.geturl() or raw_url
                html = resp.read().decode("utf-8", "ignore")
        except Exception:
            pass

    # 3. Se for link da Shopee e a API oficial estiver configurada, tenta enriquecer via ShopeeAffiliateClient
    shopee_item_match = (
        re.search(r"product/\d+/(\d+)", final_url)
        or re.search(r"-i\.\d+\.(\d+)", final_url)
        or re.search(r"/(\d{8,})(?:\?|$)", final_url)
    )
    if "shopee" in final_url.lower() and shopee_item_match:
        sh_id = shopee_item_match.group(1)
        try:
            from shopee.client import ShopeeAffiliateClient
            sh_client = ShopeeAffiliateClient()
            res_sh = sh_client.buscar_ofertas(item_id=int(sh_id), limit=1)
            if res_sh and res_sh.items:
                it = res_sh.items[0]
                return {
                    "item_id": str(it.item_id),
                    "item_name": it.product_name,
                    "price": str(it.price),
                    "image_url": it.image_url,
                    "offer_link": raw_url if ("s.shopee" in raw_url or "shp.ee" in raw_url) else (it.offer_link or raw_url),
                    "product_link": it.product_link or final_url,
                }
        except Exception:
            pass

    # 4. Extração de Metadados OpenGraph / Twitter Cards / Meta Tags
    def _extract_meta(key: str) -> str:
        patterns = [
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
        ]
        for pat in patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                return html_lib.unescape(m.group(1).strip())
        return ""

    og_title = _extract_meta("og:title")
    tw_title = _extract_meta("twitter:title")
    meta_title = _extract_meta("title")
    og_desc = _extract_meta("og:description") or _extract_meta("description")
    og_image = _extract_meta("og:image") or _extract_meta("twitter:image") or _extract_meta("image")
    price_meta = _extract_meta("product:price:amount") or _extract_meta("og:price:amount")

    # 5. Extração de Preço
    price = ""
    if price_meta:
        price = price_meta.strip()
    if not price:
        for texto_fonte in (og_title, og_desc, tw_title, html):
            if not texto_fonte:
                continue
            m_preco = re.search(r"R\$\s*([\d\.]+(?:,\d{1,2})?)", texto_fonte)
            if m_preco:
                price = m_preco.group(1).strip()
                break

    # 6. Limpeza do Título do Produto
    raw_title = tw_title or og_title or meta_title
    if not raw_title and html:
        t_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if t_m:
            raw_title = html_lib.unescape(t_m.group(1).strip())

    clean_title = raw_title or "Produto Importado via Link"
    # Remove sufixo de preço no título (ex: " - R$ 389" ou " | Mercado Livre Brasil")
    clean_title = re.sub(r"\s*-\s*R\$\s*[\d\.,]+.*$", "", clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r"\s*\|\s*(?:Mercado Livre|Shopee|Amazon).*$", "", clean_title, flags=re.IGNORECASE)
    clean_title = clean_title.strip()

    # 7. Tratamento de Imagem em Alta Resolução (especialmente Mercado Livre mlstatic.com)
    image_url = og_image
    if image_url and "mlstatic.com" in image_url and image_url.endswith(".webp"):
        # Converte miniatura -P.webp / -V.webp / -O.webp para JPEG de alta resolução (-F.jpg)
        candidate_jpg = re.sub(r"-[PVO]\.webp$", "-F.jpg", image_url)
        if candidate_jpg == image_url:
            candidate_jpg = re.sub(r"\.webp$", ".jpg", image_url)
        image_url = candidate_jpg

    # Define product_link como a URL final resolvida após redirecionamento
    product_link = final_url or raw_url

    # 8. Determinação do Item ID único
    item_id = ""
    # Prioridade 1: ID da imagem principal do ML (ex: MLA92276027266) ou MLB na URL do produto
    if image_url:
        m_img_ml = re.search(r"(ML[AB]\d{8,14})", image_url)
        if m_img_ml:
            item_id = m_img_ml.group(1)
    if not item_id:
        m_url_ml = re.search(r"(ML[AB]-?\d{7,14})", product_link, re.IGNORECASE)
        if m_url_ml:
            item_id = m_url_ml.group(1).upper().replace("-", "")
    if not item_id and shopee_item_match:
        item_id = shopee_item_match.group(1)
    if not item_id:
        # Gera ID curto determinístico a partir do link informado
        slug = re.sub(r"[^a-zA-Z0-9]", "", raw_url.rstrip("/").split("/")[-1])[:12]
        short_hash = hashlib.sha1(raw_url.encode("utf-8")).hexdigest()[:6].upper()
        item_id = f"LNK_{slug or short_hash}"

    if not image_url:
        imgs = fetch_product_images(product_link, max_images=2, item_id=item_id)
        if imgs:
            image_url = imgs[0]

    return {
        "item_id": str(item_id),
        "item_name": clean_title,
        "price": str(price or "0"),
        "image_url": image_url or "",
        "offer_link": raw_url,
        "product_link": product_link or raw_url,
    }


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
