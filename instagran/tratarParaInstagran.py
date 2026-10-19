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

# Configurações oficiais de cada formato - estritamente vinculadas a instagran/templates
FORMATOS = {
    "stories": {
        "template": TEMPLATES_DIR / "template_stories.html",
        "width": 1080,
        "height": 1920,
        "badge_default": "OFERTA RELÂMPAGO",
    },
    "post": {
        "template": TEMPLATES_DIR / "template_post.html",
        "width": 1080,
        "height": 1350,
        "badge_default": "ACHADINHO DO DIA",
    },
    "reeals": {
        "template": TEMPLATES_DIR / "template_reels.html" if (TEMPLATES_DIR / "template_reels.html").exists() else TEMPLATES_DIR / "template_reeals.html",
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


def _get_font(size: int, bold: bool = False):
    """Retorna uma fonte TrueType do sistema ou fallback padrão PIL."""
    from PIL import ImageFont
    font_names = [
        "/System/Library/Fonts/SFProText-Bold.otf" if bold else "/System/Library/Fonts/SFProText-Regular.otf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for fn in font_names:
        if Path(fn).exists():
            try:
                return ImageFont.truetype(fn, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_template_pillow(
    tipo: str,
    product_data: dict,
    output_png: Path,
    badge: str | None = None,
) -> Path:
    """Renderiza a arte gráfica seguindo o design system oficial dos templates via Pillow (alta fidelidade e sem falhas de navegador)."""
    from PIL import Image, ImageDraw, ImageOps
    import io

    tipo_norm = tipo.lower()
    config = FORMATOS.get(tipo_norm, FORMATOS["stories"])
    width = config["width"]
    height = config["height"]
    badge_text = (badge or config["badge_default"]).upper()

    title = product_data.get("title") or product_data.get("item_name") or "Oferta Especial Shopee"
    image_url = product_data.get("image_url") or ""
    price_raw = product_data.get("price") or "OFERTA"
    price_str = str(price_raw).replace("R$", "").strip()

    # 1. Base do Canvas com fundo suave #F8FAFC
    img = Image.new("RGBA", (width, height), (248, 250, 252, 255))
    draw = ImageDraw.Draw(img)

    # Decorações de fundo (acentos circulares suaves em degradê)
    draw.ellipse([-200, -200, 600, 600], fill=(2, 99, 224, 18))
    draw.ellipse([width - 400, height // 3, width + 300, height // 3 + 700], fill=(255, 110, 46, 20))
    draw.ellipse([-150, height - 500, 450, height + 100], fill=(2, 99, 224, 15))

    # Borda externa sutil
    draw.rounded_rectangle([30, 30, width - 30, height - 30], radius=32, outline=(226, 232, 240, 255), width=3)

    # 2. Inclusão da logo oficial dicacerta.png
    logo_path = None
    for cand in [TEMPLATES_DIR / "dicacerta.png", MODULE_DIR / "dicacerta.png", ROOT / "dicacerta.png"]:
        if cand.exists():
            logo_path = cand
            break

    y_cursor = 80
    if logo_path:
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            # Redimensiona mantendo proporção (largura ~260px)
            logo_w = 260
            logo_h = int(logo_img.height * (logo_w / logo_img.width))
            logo_img = logo_img.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            img.paste(logo_img, ((width - logo_w) // 2, y_cursor), logo_img)
            y_cursor += logo_h + 35
        except Exception:
            y_cursor += 60
    else:
        y_cursor += 40

    # 3. Badge / Selo de Oferta
    badge_font = _get_font(28, bold=True)
    # Medir texto do badge
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = (bbox[2] - bbox[0]) + 48
    bh = (bbox[3] - bbox[1]) + 24
    bx = (width - bw) // 2
    by = y_cursor

    # Fundo do badge (Laranja Shopee com cantos arredondados)
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=20, fill=(238, 77, 45, 255))
    draw.text((bx + 24, by + 10), badge_text, font=badge_font, fill=(255, 255, 255, 255))
    y_cursor = by + bh + 45

    # 4. Card Central do Produto com foto
    card_margin = 80
    card_w = width - (card_margin * 2)
    card_h = 820 if tipo_norm in ("stories", "reeals", "reels") else 620
    card_x = card_margin
    card_y = y_cursor

    # Sombra e fundo branco do card
    draw.rounded_rectangle([card_x + 6, card_y + 12, card_x + card_w + 6, card_y + card_h + 12], radius=32, fill=(203, 213, 225, 120))
    draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=32, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=2)

    # Carregamento da foto do produto
    prod_image = None
    if image_url:
        if isinstance(image_url, (str, Path)) and Path(str(image_url)).exists():
            try:
                prod_image = Image.open(str(image_url)).convert("RGBA")
            except Exception:
                prod_image = None
        elif isinstance(image_url, str) and (image_url.startswith("http://") or image_url.startswith("https://")):
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Referer": "https://shopee.com.br/",
                }
                req = urllib.request.Request(image_url, headers=headers)
                with urllib.request.urlopen(req, timeout=12) as resp:
                    prod_bytes = resp.read()
                    prod_image = Image.open(io.BytesIO(prod_bytes)).convert("RGBA")
            except Exception:
                prod_image = None


    if prod_image:
        try:
            # Ajusta no interior do card mantendo padding
            pad = 40
            max_pw = card_w - (pad * 2)
            max_ph = card_h - (pad * 2)
            prod_image.thumbnail((max_pw, max_ph), Image.Resampling.LANCZOS)
            px = card_x + (card_w - prod_image.width) // 2
            py = card_y + (card_h - prod_image.height) // 2
            img.paste(prod_image, (px, py), prod_image)
        except Exception:
            pass
    else:
        # Placeholder estético
        draw.text((card_x + card_w // 2 - 120, card_y + card_h // 2 - 20), "Foto do Produto", font=_get_font(36, bold=True), fill=(148, 163, 184, 255))

    y_cursor = card_y + card_h + 50

    # 5. Título do Produto (com quebra inteligente de linha)
    title_font = _get_font(36, bold=True)
    words = title.split()
    lines = []
    curr = []
    for w in words:
        test_line = " ".join(curr + [w])
        t_box = draw.textbbox((0, 0), test_line, font=title_font)
        if (t_box[2] - t_box[0]) > (width - 160):
            lines.append(" ".join(curr))
            curr = [w]
        else:
            curr.append(w)
    if curr:
        lines.append(" ".join(curr))
    lines = lines[:2] # Máximo 2 linhas

    for line in lines:
        t_box = draw.textbbox((0, 0), line, font=title_font)
        tx = (width - (t_box[2] - t_box[0])) // 2
        draw.text((tx, y_cursor), line, font=title_font, fill=(15, 42, 74, 255))
        y_cursor += 50

    y_cursor += 20

    # 6. Bloco de Preço com Destaque
    price_label_font = _get_font(26, bold=False)
    price_val_font = _get_font(68, bold=True)
    
    draw.text(((width - 180) // 2, y_cursor), "POR APENAS", font=price_label_font, fill=(100, 116, 139, 255))
    y_cursor += 38

    price_full_txt = f"R$ {price_str}"
    p_box = draw.textbbox((0, 0), price_full_txt, font=price_val_font)
    px = (width - (p_box[2] - p_box[0])) // 2
    draw.text((px, y_cursor), price_full_txt, font=price_val_font, fill=(238, 77, 45, 255))
    y_cursor += 100

    # 7. Botão de Chamada para Ação (CTA)
    cta_w = width - 180
    cta_h = 100
    cta_x = 90
    cta_y = height - 190 if tipo_norm in ("stories", "reeals", "reels") else y_cursor + 20

    draw.rounded_rectangle([cta_x, cta_y, cta_x + cta_w, cta_y + cta_h], radius=26, fill=(2, 99, 224, 255))
    cta_txt = "🔥 GARANTA O SEU • LINK OFICIAL"
    cta_font = _get_font(32, bold=True)
    c_box = draw.textbbox((0, 0), cta_txt, font=cta_font)
    cx = cta_x + (cta_w - (c_box[2] - c_box[0])) // 2
    cy = cta_y + (cta_h - (c_box[3] - c_box[1])) // 2 - 2
    draw.text((cx, cy), cta_txt, font=cta_font, fill=(255, 255, 255, 255))

    # Salva imagem final RGB de alta qualidade
    output_png = Path(output_png).resolve()
    output_png.parent.mkdir(parents=True, exist_ok=True)
    final_rgb = img.convert("RGB")
    final_rgb.save(output_png, format="PNG", quality=95)
    return output_png


def render_template_to_image(
    tipo: str,
    product_data: dict,
    output_png: Path,
    badge: str | None = None,
) -> Path:
    """Renderiza a imagem oficial com base nos templates, usando Chrome Headless ou fallback gráfico Pillow garantido."""
    output_png = Path(output_png).resolve()
    output_png.parent.mkdir(parents=True, exist_ok=True)

    tipo_norm = tipo.lower()
    if tipo_norm not in FORMATOS:
        raise ValueError(f"Tipo desconhecido: '{tipo}'. Tipos válidos: {list(FORMATOS.keys())}")

    config = FORMATOS[tipo_norm]
    template_file = config["template"]
    if not template_file.exists():
        raise FileNotFoundError(f"Template obrigatório não encontrado em instagran/templates: {template_file}")

    # 1. Tentativa via Chrome Headless com isolamento total de perfil
    chrome_candidatos = [
        os.environ.get("CHROME_PATH"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    chrome_bin = next((c for c in chrome_candidatos if c and Path(c).exists()), None)

    if chrome_bin and template_file.exists():
        temp_profile = ROOT / "db" / "img" / ".chrome_tmp_profile"
        temp_profile.mkdir(parents=True, exist_ok=True)
        temp_html = output_png.parent / f"_temp_{output_png.stem}.html"

        try:
            template_content = template_file.read_text(encoding="utf-8")
            title = product_data.get("title") or product_data.get("item_name") or "Produto Shopee"
            image_url = product_data.get("image_url") or ""
            price = str(product_data.get("price") or "Confira no Link").replace("R$", "").strip()
            link = product_data.get("url") or product_data.get("offer_link") or "#"
            badge_text = badge or config["badge_default"]

            # Converte a imagem do produto para base64 Data URI para exibição garantida e sem bloqueio no Chrome
            prod_data_uri = image_url
            if image_url and Path(str(image_url)).exists():
                local_p = Path(str(image_url))
                mime = "image/png" if local_p.suffix.lower() == ".png" else "image/jpeg"
                b64_prod = base64.b64encode(local_p.read_bytes()).decode("ascii")
                prod_data_uri = f"data:{mime};base64,{b64_prod}"
            elif image_url and (str(image_url).startswith("http://") or str(image_url).startswith("https://")):
                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        "Referer": "https://shopee.com.br/",
                    }
                    req = urllib.request.Request(image_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        b64_prod = base64.b64encode(resp.read()).decode("ascii")
                        prod_data_uri = f"data:image/jpeg;base64,{b64_prod}"
                except Exception:
                    prod_data_uri = image_url

            # Logo oficial da pasta instagran/templates
            logo_path = TEMPLATES_DIR / "dicacerta.png"
            if not logo_path.exists():
                logo_path = MODULE_DIR / "dicacerta.png"
            b64_logo = base64.b64encode(logo_path.read_bytes()).decode("ascii")
            logo_data_uri = f"data:image/png;base64,{b64_logo}"

            rendered_html = template_content \
                .replace("{{PRODUCT_TITLE}}", title) \
                .replace("{{PRODUCT_IMAGE}}", prod_data_uri) \
                .replace("{{PRODUCT_PRICE}}", price) \
                .replace("{{PRODUCT_LINK}}", link) \
                .replace("{{PRODUCT_BADGE}}", badge_text) \
                .replace("{{BRAND_LOGO}}", logo_data_uri) \
                .replace("dicacerta.png", logo_data_uri)

            temp_html.write_text(rendered_html, encoding="utf-8")

            cmd = [
                chrome_bin,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
                f"--user-data-dir={temp_profile}",
                "--hide-scrollbars",
                f"--window-size={config['width']},{config['height']}",
                f"--screenshot={output_png}",
                f"file://{temp_html.resolve()}",
            ]

            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            if output_png.exists() and output_png.stat().st_size > 1000:
                print(f"   🎨 Renderizado com sucesso a partir do template oficial: {template_file.name}")
                return output_png
        except Exception as e:
            print(f"   ⚠️ Aviso: falha na renderização de {template_file.name} via Chrome ({e}). Acionando fallback gráfico.")
        finally:
            if temp_html.exists():
                try:
                    temp_html.unlink()
                except OSError:
                    pass

    # 2. Fallback de Alta Fidelidade com Pillow (Garante geração 100% à prova de falhas)
    return render_template_pillow(tipo, product_data, output_png, badge=badge)


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

    # 3. Garante que a foto do produto existe e está cacheada em disco
    image_url = product_data.get("image_url") or ""
    original_img_path = destino_dir / "original.jpg"

    # Se já existir cache local íntegro da foto original do produto, reutiliza imediatamente
    if original_img_path.exists() and original_img_path.stat().st_size > 1000:
        image_url = str(original_img_path)
        product_data["image_url"] = image_url


    # Se a imagem ainda estiver ausente, tenta extrair via reader
    if not image_url:
        prod_link = product_data.get("product_link") or product_data.get("url") or ""
        if prod_link:
            try:
                from produtos.reader import fetch_product_images
                imgs = fetch_product_images(prod_link, max_images=2, item_id=codigo_usado)
                if imgs:
                    image_url = imgs[0]
                    product_data["image_url"] = image_url
                    try:
                        from db.controle import atualizar_imagem_produto
                        atualizar_imagem_produto(codigo_usado, image_url)
                    except Exception:
                        pass
            except Exception as e:
                print(f"Aviso ao buscar imagem para {codigo_usado}: {e}")

    # Se for uma URL remota, baixa e salva como original.jpg no diretório do produto
    if image_url and (str(image_url).startswith("http://") or str(image_url).startswith("https://")):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Referer": "https://shopee.com.br/",
            }
            req = urllib.request.Request(image_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                original_img_path.write_bytes(resp.read())
                image_url = str(original_img_path)
                product_data["image_url"] = image_url
        except Exception as e:
            print(f"Aviso ao baixar foto original para {codigo_usado}: {e}")

    # 4. Renderiza imagens para os 3 formatos oficiais
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

    # 5. Gera o vídeo MP4 oficial de Reels a partir da imagem gerada usando ffmpeg
    reels_mp4 = destino_dir / f"{codigo_usado}_reeals.mp4"
    reels_source_img = resultados.get("reeals") or resultados.get("stories")
    if reels_source_img and reels_source_img.exists():
        try:
            cmd_ffmpeg = [
                "ffmpeg",
                "-y",
                "-loop", "1",
                "-i", str(reels_source_img),
                "-c:v", "libx264",
                "-t", "5",
                "-pix_fmt", "yuv420p",
                "-vf", "scale=1080:1920",
                str(reels_mp4),
            ]
            subprocess.run(cmd_ffmpeg, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
            if reels_mp4.exists() and reels_mp4.stat().st_size > 1000:
                resultados["reels_mp4"] = reels_mp4
                resultados["reeals_mp4"] = reels_mp4
                alias_mp4 = destino_dir / f"{codigo_usado}_reels.mp4"
                if not alias_mp4.exists():
                    alias_mp4.write_bytes(reels_mp4.read_bytes())
        except Exception as e:
            print(f"Aviso ao gerar vídeo MP4 de Reels via ffmpeg: {e}")

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
