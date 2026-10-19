#!/usr/bin/env python3
"""tratarParaInstagran: Gera imagens personalizadas para Stories, Post e Reels com base em templates oficiais."""
import argparse
import base64
import datetime
import json
import os
import random
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = MODULE_DIR / "templates"
IMG_DIR = MODULE_DIR / "img"

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
USER_AGENT = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"

DEFAULT_EXAMPLE_URL = "https://shopee.com.br/product/1531212217/23198452214"

# Configurações oficiais de cada formato
FORMATOS = {
    "stories": {
        "template": TEMPLATES_DIR / "template_stories.html",
        "fallback_template": MODULE_DIR / "template.html",
        "width": 1080,
        "height": 1920,
        "badge_default": "OFERTA RELÂMPAGO",
    },
    "post": {
        "template": TEMPLATES_DIR / "template_post.html",
        "fallback_template": MODULE_DIR / "template.html",
        "width": 1080,
        "height": 1350,
        "badge_default": "ACHADINHO DO DIA",
    },
    "reeals": {
        "template": TEMPLATES_DIR / "template_reeals.html",
        "fallback_template": MODULE_DIR / "template.html",
        "width": 1080,
        "height": 1920,
        "badge_default": "REELS OFERTA",
    },
}
# Alias para reels
FORMATOS["reels"] = FORMATOS["reeals"]


def gerar_codigo_unico(img_dir: Path | None = None) -> str:
    """Gera um número aleatório único de 6 dígitos que ainda não tenha sido usado como prefixo de imagem."""
    busca_dir = img_dir or (ROOT / "db" / "img")
    busca_dir.mkdir(parents=True, exist_ok=True)
    existentes = set()
    for f in busca_dir.glob("**/*_*.*"):
        prefix = f.name.split("_")[0]
        if prefix.isdigit():
            existentes.add(prefix)

    while True:
        codigo = str(random.randint(100000, 999999))
        if codigo not in existentes:
            return codigo


def fetch_product_info(url: str) -> dict:
    """Extrai título, imagem e informações da página da Shopee com fallback para curl."""
    html = ""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", "ignore")
    except Exception:
        # Fallback via curl quando urllib for bloqueado
        try:
            res = subprocess.run(
                ["curl", "-sL", "-A", USER_AGENT, url],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if res.returncode == 0:
                html = res.stdout
        except Exception:
            html = ""

    # 1. Título do produto
    title = ""
    title_match = re.search(r'property=[\"\']og:title[\"\']\s+content=[\"\']([^\"\']+)[\"\']', html) or \
                  re.search(r'content=[\"\']([^\"\']+)[\"\']\s+property=[\"\']og:title[\"\']', html)
    if title_match:
        title = title_match.group(1).replace(" | Shopee Brasil", "").strip()
    if not title:
        title = "Oferta Especial Shopee"

    # 2. Imagem principal
    image_url = ""
    img_match = re.search(r'property=[\"\']og:image[\"\']\s+content=[\"\']([^\"\']+)[\"\']', html) or \
                re.search(r'content=[\"\']([^\"\']+)[\"\']\s+property=[\"\']og:image[\"\']', html)
    if img_match:
        image_url = img_match.group(1).strip()
    else:
        # Fallback padrão CDN
        ids = re.findall(r'(?:br|sg|my|id|ph|th|vn)-[0-9]+-[a-z0-9-]+', html)
        if ids:
            image_url = f"https://down-br.img.susercontent.com/file/{ids[0]}"

    # 3. Preço aproximado
    price = ""
    prices = re.findall(r'R\$\s*([\d\.,]+)', html)
    if prices:
        price = prices[0].replace("R$", "").strip()

    return {
        "title": title,
        "image_url": image_url,
        "price": price or "OFERTA",
        "url": url,
    }


def render_template_to_image(
    tipo: str,
    product_data: dict,
    output_png: Path,
    badge: str | None = None,
) -> Path:
    """Renderiza um template específico (stories, post ou reeals) em PNG com o Chrome Headless."""
    tipo_norm = tipo.lower()
    if tipo_norm not in FORMATOS:
        raise ValueError(f"Tipo desconhecido: '{tipo}'. Tipos válidos: {list(FORMATOS.keys())}")

    config = FORMATOS[tipo_norm]
    template_file = config["template"]
    if not template_file.exists():
        template_file = config["fallback_template"]
    if not template_file.exists():
        raise FileNotFoundError(f"Template não encontrado: {template_file}")

    template_content = template_file.read_text(encoding="utf-8")

    title = product_data.get("title") or product_data.get("item_name") or "Produto Shopee"
    image_url = product_data.get("image_url") or ""
    price = product_data.get("price") or "Confira no Link"
    if isinstance(price, str):
        price = price.replace("R$", "").strip()
    link = product_data.get("url") or product_data.get("offer_link") or "#"
    badge_text = badge or config["badge_default"]

    # Codifica a logo da marca em Base64 para evitar qualquer falha de caminho relativo no Chrome Headless
    logo_data_uri = "dicacerta.png"
    for candidate in [TEMPLATES_DIR / "dicacerta.png", MODULE_DIR / "dicacerta.png", ROOT / "dicacerta.png"]:
        if candidate.exists():
            b64_logo = base64.b64encode(candidate.read_bytes()).decode("ascii")
            logo_data_uri = f"data:image/png;base64,{b64_logo}"
            break

    rendered_html = template_content \
        .replace("{{PRODUCT_TITLE}}", title) \
        .replace("{{PRODUCT_IMAGE}}", image_url) \
        .replace("{{PRODUCT_PRICE}}", price) \
        .replace("{{PRODUCT_LINK}}", link) \
        .replace("{{PRODUCT_BADGE}}", badge_text) \
        .replace("{{BRAND_LOGO}}", logo_data_uri) \
        .replace("dicacerta.png", logo_data_uri)

    # Cria arquivo HTML intermediário na mesma pasta do template para manter resolução de fontes e assets
    output_png = Path(output_png).resolve()
    output_png.parent.mkdir(parents=True, exist_ok=True)

    temp_html = output_png.parent / f"_temp_{output_png.stem}.html"
    temp_html.write_text(rendered_html, encoding="utf-8")

    if not Path(CHROME_PATH).exists():
        raise RuntimeError(f"Google Chrome não encontrado em {CHROME_PATH}")

    width = config["width"]
    height = config["height"]

    cmd = [
        CHROME_PATH,
        "--headless",
        "--disable-gpu",
        "--hide-scrollbars",
        "--virtual-time-budget=2500",
        f"--window-size={width},{height}",
        f"--screenshot={output_png}",
        f"file://{temp_html.resolve()}",
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        if temp_html.exists():
            try:
                temp_html.unlink()
            except OSError:
                pass

    if not output_png.exists():
        raise RuntimeError(f"Falha ao gerar a imagem {output_png}")

    return output_png


def gerar_todas_imagens(
    product_data: dict,
    output_dir: Path | None = None,
    codigo: str | None = None,
    data_str: str | None = None,
) -> dict[str, Path]:
    """Gera as imagens oficiais (stories, post e reeals) em db/img/<data>/<Item Id>/ com nome baseado no Item Id."""
    # 1. Identificador: Prioridade para 'Item Id', fallback para aleatório se ausente
    item_id_candidato = str(
        product_data.get("item_id")
        or product_data.get("Item Id")
        or product_data.get("Item ID")
        or codigo
        or ""
    ).strip()

    if not item_id_candidato or item_id_candidato.lower() in ("none", "null"):
        codigo_usado = gerar_codigo_unico()
    else:
        codigo_usado = item_id_candidato

    # 2. Diretório de destino: /db/img/<data>/<Item Id>/
    if output_dir is None:
        data_ref = data_str or datetime.date.today().strftime("%Y-%m-%d")
        destino_dir = ROOT / "db" / "img" / data_ref / codigo_usado
    else:
        destino_dir = Path(output_dir).resolve()

    destino_dir.mkdir(parents=True, exist_ok=True)
    resultados = {
        "codigo": codigo_usado,
        "pasta": destino_dir,
    }

    for tipo in ["stories", "post", "reeals"]:
        nome_arquivo = f"{codigo_usado}_{tipo}.png"
        destino_png = destino_dir / nome_arquivo
        render_template_to_image(tipo, product_data, destino_png)
        resultados[tipo] = destino_png

    # Cria cópia de conveniência com grafia reels se necessário
    reels_alias = destino_dir / f"{codigo_usado}_reels.png"
    if resultados["reeals"].exists() and not reels_alias.exists():
        reels_alias.write_bytes(resultados["reeals"].read_bytes())
        resultados["reels"] = reels_alias

    return resultados


def render_story_image(
    product_data: dict,
    output_png: Path,
    output_html: Path | None = None,
    badge: str = "OFERTA RELÂMPAGO",
) -> Path:
    """Função de compatibilidade com chamadas legadas."""
    return render_template_to_image("stories", product_data, output_png, badge=badge)


def main():
    parser = argparse.ArgumentParser(description="Gera imagens oficiais para Instagram (Stories, Post, Reels) a partir de link Shopee.")
    parser.add_argument("url", nargs="?", default=DEFAULT_EXAMPLE_URL, help="Link do produto Shopee.")
    parser.add_argument("--item-id", default=None, help="Item Id oficial do produto para nomear as imagens.")
    parser.add_argument("--price", default=None, help="Preço manual para exibir no card (ex: 49,90).")
    parser.add_argument("--badge", default=None, help="Texto do selo superior.")
    parser.add_argument("--tipo", choices=["stories", "post", "reeals", "reels", "todos"], default="todos", help="Formato de imagem a gerar.")
    parser.add_argument("--output-dir", default=None, help="Pasta de saída das imagens (padrão: db/img/<data>/<Item Id>).")
    args = parser.parse_args()

    print(f"🔗 Extraindo informações do link: {args.url}")
    info = fetch_product_info(args.url)

    if args.item_id:
        info["item_id"] = args.item_id
    if args.price:
        info["price"] = args.price

    print(f"📦 Título: {info['title']}")
    print(f"🖼️  Imagem: {info['image_url']}")
    print(f"💰 Preço: {info['price']}")

    if args.tipo in ["todos", "all"]:
        print("🎨 Gerando todas as imagens (Stories, Post e Reels)...")
        res = gerar_todas_imagens(info, output_dir=Path(args.output_dir) if args.output_dir else None)
        print(f"✅ Identificador: {res['codigo']}")
        print(f"📁 Pasta de destino: {res['pasta']}")
        print(f"   📸 Stories: {res['stories']}")
        print(f"   🖼️  Post:    {res['post']}")
        print(f"   🎬 Reels:   {res['reeals']}")
    else:
        identificador = args.item_id or gerar_codigo_unico()
        data_ref = datetime.date.today().strftime("%Y-%m-%d")
        destino_dir = Path(args.output_dir) if args.output_dir else (ROOT / "db" / "img" / data_ref / identificador)
        destino_dir.mkdir(parents=True, exist_ok=True)
        nome = f"{identificador}_{args.tipo}.png"
        destino = destino_dir / nome
        print(f"🎨 Gerando {args.tipo} em {destino}...")
        render_template_to_image(args.tipo, info, destino, badge=args.badge)
        print(f"✅ Imagem gerada com sucesso: {destino}")


if __name__ == "__main__":
    main()
