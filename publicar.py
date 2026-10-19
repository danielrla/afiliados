#!/usr/bin/env python3
"""Script de automação unificado de publicações para Shopee Afiliados.

Publica sequencialmente em:
1. WhatsApp (Grupo via Z-API)
2. Facebook (Página)
3. Instagram (Stories, Post no Feed e Reels gerados via tratarParaInstagran)
"""
import argparse
import csv
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from shopee.client import load_env
from facebook.client import FacebookPageClient
from instagran.client import InstagramClient
from whatsapp.client import ZApiClient
from produtos.reader import fetch_product_images
from instagran.tratarParaInstagran import gerar_todas_imagens, render_story_image
from db.controle import (
    inicializar_banco,
    registrar_produto,
    obter_produto,
    atualizar_codigo_artes,
    obter_status_canais,
    registrar_resultado_canal,
    obter_produtos_para_reprocessamento,
    gerar_relatorio_terminal,
    localizar_artes_produto,
    CANAIS_OBRIGATORIOS,
)


def parse_csv(csv_path: Path) -> list[dict]:
    """Lê o arquivo CSV tratando variações de BOM e linhas encapsuladas em aspas."""
    import re

    if not csv_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {csv_path}")

    products = []
    with csv_path.open(encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            header = [h.strip() for h in next(reader)]
        except StopIteration:
            return []

        for row in reader:
            if not row:
                continue
            # Tratamento para linhas com escape total de aspas externas
            if len(row) == 1 and "," in row[0]:
                row = next(csv.reader([row[0]]))

            data = dict(zip(header, [c.strip() for c in row]))
            item_name = data.get("Item Name", "").strip()
            offer_link = data.get("Offer Link", "").strip()
            product_link = data.get("Product Link", "").strip()
            price = data.get("Price", "").strip()

            if not item_name or not offer_link:
                continue

            # Extração do item_id único
            item_id = data.get("Item Id") or data.get("Item ID") or data.get("item_id") or ""
            if not item_id and product_link:
                m = re.search(r'/(\d{8,})(?:\?|$)', product_link)
                if m:
                    item_id = m.group(1)
            if not item_id:
                item_id = offer_link.strip("/").split("/")[-1]

            products.append({
                "item_id": item_id,
                "item_name": item_name,
                "offer_link": offer_link,
                "product_link": product_link,
                "price": price,
            })

    return products


def format_caption(item_name: str, offer_link: str, price: str | None = None) -> str:
    """Gera legenda padronizada e atraente para as redes sociais."""
    preco_txt = f"\n💰 Por apenas R$ {price}" if price else ""
    return (
        f"🔥 *{item_name}*{preco_txt}\n\n"
        f"Garanta o seu com desconto no link oficial da Shopee:\n"
        f"👉 {offer_link}"
    )


def publicar_produto(
    produto: dict,
    fb_client: FacebookPageClient,
    ig_client: InstagramClient,
    wa_client: ZApiClient,
    dry_run: bool = False,
) -> dict:
    """Executa a sequência de publicações para um único produto com controle granular de status."""
    item_id = str(produto.get("item_id") or produto.get("offer_link", "").strip("/").split("/")[-1])
    produto["item_id"] = item_id
    item_name = produto["item_name"]
    offer_link = produto["offer_link"]
    product_link = produto["product_link"]
    price = produto.get("price")

    # Registra ou atualiza o produto no SQLite em execuções reais
    if not dry_run:
        registrar_produto(produto)
    status_canais = obter_status_canais(item_id)

    # Verifica se já está 100% concluído em todos os canais obrigatórios
    concluidos = [c for c in CANAIS_OBRIGATORIOS if status_canais.get(c) == "SUCESSO"]
    if len(concluidos) == len(CANAIS_OBRIGATORIOS):
        print(f"\n==========================================")
        print(f"⏩ [100% CONCLUÍDO] {item_name} (ID: {item_id})")
        print("   Todos os 5 canais já foram publicados com sucesso anteriormente. Pulando.")
        return {"item_name": item_name, "status": "JA_CONCLUIDO"}

    print(f"\n==========================================")
    print(f"📦 Processando: {item_name} (ID: {item_id})")
    print(f"🔗 Link de Afiliado: {offer_link}")
    pendentes = [c for c in CANAIS_OBRIGATORIOS if status_canais.get(c) != "SUCESSO"]
    print(f"📋 Canais pendentes ({len(pendentes)}): {', '.join(pendentes)}")

    # 1. Obtenção das imagens do produto
    print("🖼️  Buscando imagens do produto na Shopee...")
    primary_image = produto.get("image_url")
    if not primary_image and product_link:
        images = fetch_product_images(product_link, max_images=4, item_id=item_id)
        if images:
            primary_image = images[0]
            try:
                from db.controle import atualizar_imagem_produto
                atualizar_imagem_produto(item_id, primary_image)
            except Exception:
                pass

    if not primary_image:
        print("⚠️ Nenhuma imagem identificada para o produto. Prosseguindo com envio de texto onde aplicável.")

    caption = format_caption(item_name, offer_link, price)
    resultado = {
        "item_name": item_name,
        "whatsapp": None,
        "facebook": None,
        "instagram_stories": None,
        "instagram_post": None,
        "instagram_reels": None,
    }

    # 1. Localização ou geração das artes oficiais do Instagram em db/img
    artes = localizar_artes_produto(item_id, produto.get("pasta_artes"))
    precisa_instagram = any(status_canais.get(c) != "SUCESSO" for c in ["instagram_stories", "instagram_post", "instagram_reels"])
    if precisa_instagram and (not artes.get("stories") or not artes.get("post") or not artes.get("reels")):
        print("🎨 Gerando artes oficiais para Instagram (Stories, Post e Reels) com template...")
        try:
            clean_price = price.replace("R$", "").strip() if price else "OFERTA"
            artes = gerar_todas_imagens({
                "item_id": item_id,
                "title": item_name,
                "image_url": primary_image,
                "price": clean_price,
                "url": offer_link,
            })
            pasta_artes_str = str(artes.get("pasta")) if artes.get("pasta") else None
            atualizar_codigo_artes(item_id, artes.get("codigo"), pasta_artes=pasta_artes_str)
            print(f"   ✅ Identificador: {artes.get('codigo')}")
            print(f"   📁 Salvo em db/img: {artes.get('pasta')}")
            print(f"   📸 Stories:      {artes.get('stories').name}")
            print(f"   🖼️  Post:         {artes.get('post').name}")
            reels_nome = artes.get('reels', artes.get('reeals')).name if artes.get('reels') or artes.get('reeals') else 'reels'
            print(f"   🎬 Reels:        {reels_nome}")
        except Exception as e:
            print(f"   ⚠️ Falha na geração das imagens pelo template: {e}")

    if dry_run:
        print("[DRY-RUN] Simulação ativa. Nenhuma publicação externa enviada.")
        if artes:
            print(f"   🖼️  [DRY-RUN] Artes salvas em: {artes.get('pasta')}")
        return resultado

    # 1 - Publicar no grupo do whatsapp:
    # 1.1 - Publicar o link no grupo.
    caminho_wa = primary_image if primary_image else None
    if status_canais.get("whatsapp") == "SUCESSO":
        print("💬 [1/3] WhatsApp: Já publicado anteriormente com sucesso. Pulando.")
    else:
        print("💬 [1/3] Publicando no WhatsApp...")
        try:
            res_wa = wa_client.send_to_group(caption, image_url=primary_image)
            msg_id = res_wa.get("messageId") or res_wa.get("zaapId")
            resultado["whatsapp"] = msg_id
            registrar_resultado_canal(item_id, "whatsapp", "SUCESSO", id_externo=msg_id, caminho_imagem=caminho_wa)
            print(f"   ✅ WhatsApp: Sucesso (ID: {msg_id})")
        except Exception as e:
            registrar_resultado_canal(item_id, "whatsapp", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_wa)
            print(f"   ❌ WhatsApp: Falha ({e})")

    # 2 - Publicar no facebook:
    # 2.2 - Postar com a Descricao do produto, imagens e link do produto.
    caminho_fb = primary_image if primary_image else None
    if status_canais.get("facebook") == "SUCESSO":
        print("📘 [2/3] Facebook: Já publicado anteriormente com sucesso. Pulando.")
    else:
        print("📘 [2/3] Publicando no Facebook...")
        try:
            if primary_image:
                res_fb = fb_client.publish_photo(primary_image, caption)
            else:
                res_fb = fb_client.publish_post(caption, link=offer_link)
            post_id = res_fb.get("post_id") or res_fb.get("id")
            resultado["facebook"] = post_id
            registrar_resultado_canal(item_id, "facebook", "SUCESSO", id_externo=post_id, caminho_imagem=caminho_fb)
            print(f"   ✅ Facebook: Sucesso (ID: {post_id})")
        except Exception as e:
            registrar_resultado_canal(item_id, "facebook", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_fb)
            print(f"   ❌ Facebook: Falha ({e})")

    # 3 - Publicar no Instagram:
    print("📸 [3/3] Publicando no Instagram...")
    story_png = artes.get("stories")
    post_png = artes.get("post")
    reels_png = artes.get("reeals") or artes.get("reels")

    # 3.2.2 - Stories: com a imagem da etapa anterior
    caminho_story = str(story_png) if (story_png and story_png.exists()) else (primary_image if primary_image else None)
    if status_canais.get("instagram_stories") == "SUCESSO":
        print("   ⏩ [Instagram 1/3] Stories: Já publicado anteriormente. Pulando.")
    else:
        print("   📲 [Instagram 1/3] Publicando Stories...")
        try:
            if story_png and story_png.exists():
                story_cdn_url = fb_client.upload_photo_to_cdn(story_png)
                res_ig_story = ig_client.publish_story(story_cdn_url)
                story_id = res_ig_story.get("id")
                resultado["instagram_stories"] = story_id
                registrar_resultado_canal(item_id, "instagram_stories", "SUCESSO", id_externo=story_id, caminho_imagem=caminho_story)
                print(f"      ✅ Stories: Publicado com template! (ID: {story_id})")
            elif primary_image:
                res_ig_story = ig_client.publish_story(primary_image)
                story_id = res_ig_story.get("id")
                resultado["instagram_stories"] = story_id
                registrar_resultado_canal(item_id, "instagram_stories", "SUCESSO", id_externo=story_id, caminho_imagem=caminho_story)
                print(f"      ✅ Stories: Publicado com imagem original! (ID: {story_id})")
            else:
                registrar_resultado_canal(item_id, "instagram_stories", "FALHA", mensagem_erro="Imagem ausente para renderizar template de Stories", caminho_imagem=caminho_story)
                print("      ⚠️ Stories: Ignorado (sem imagem).")
        except Exception as e:
            registrar_resultado_canal(item_id, "instagram_stories", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_story)
            print(f"      ❌ Stories: Falha ({e})")

    # 3.2.3 - Post: Publicar a imagem da etapa anterior
    caminho_post = str(post_png) if (post_png and post_png.exists()) else (primary_image if primary_image else None)
    if status_canais.get("instagram_post") == "SUCESSO":
        print("   ⏩ [Instagram 2/3] Post: Já publicado anteriormente. Pulando.")
    else:
        print("   🖼️  [Instagram 2/3] Publicando Post no Feed...")
        try:
            if post_png and post_png.exists():
                post_cdn_url = fb_client.upload_photo_to_cdn(post_png)
                res_ig_post = ig_client.publish_photo(post_cdn_url, caption)
                post_id = res_ig_post.get("id")
                resultado["instagram_post"] = post_id
                registrar_resultado_canal(item_id, "instagram_post", "SUCESSO", id_externo=post_id, caminho_imagem=caminho_post)
                print(f"      ✅ Post no Feed: Publicado com template! (ID: {post_id})")
            elif primary_image:
                res_ig_post = ig_client.publish_photo(primary_image, caption)
                post_id = res_ig_post.get("id")
                resultado["instagram_post"] = post_id
                registrar_resultado_canal(item_id, "instagram_post", "SUCESSO", id_externo=post_id, caminho_imagem=caminho_post)
                print(f"      ✅ Post no Feed: Publicado com imagem original! (ID: {post_id})")
            else:
                registrar_resultado_canal(item_id, "instagram_post", "FALHA", mensagem_erro="Imagem ausente para renderizar template de Post Feed", caminho_imagem=caminho_post)
                print("      ⚠️ Post no Feed: Ignorado (sem imagem).")
        except Exception as e:
            registrar_resultado_canal(item_id, "instagram_post", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_post)
            print(f"      ❌ Post no Feed: Falha ({e})")

    # 3.2.4 - Reals: Publicar a imagem da etapa anterior
    target_reels_img = reels_png if (reels_png and reels_png.exists()) else story_png
    video_reels_mp4 = target_reels_img.with_suffix(".mp4") if target_reels_img else None
    caminho_reels = str(video_reels_mp4) if (video_reels_mp4 and video_reels_mp4.exists()) else (str(target_reels_img) if target_reels_img else None)
    if status_canais.get("instagram_reels") == "SUCESSO":
        print("   ⏩ [Instagram 3/3] Reels: Já publicado anteriormente. Pulando.")
    else:
        print("   🎬 [Instagram 3/3] Publicando Reels...")
        try:
            if target_reels_img and target_reels_img.exists():
                res_ig_reels = ig_client.publish_reel_from_image(target_reels_img, caption)
                reels_id = res_ig_reels.get("id")
                resultado["instagram_reels"] = reels_id
                # Atualiza caminho_reels caso o mp4 tenha sido gerado durante a chamada
                if video_reels_mp4 and video_reels_mp4.exists():
                    caminho_reels = str(video_reels_mp4)
                registrar_resultado_canal(item_id, "instagram_reels", "SUCESSO", id_externo=reels_id, caminho_imagem=caminho_reels)
                print(f"      ✅ Reels: Publicado com sucesso! (ID: {reels_id})")
            else:
                registrar_resultado_canal(item_id, "instagram_reels", "FALHA", mensagem_erro="Imagem compatível ausente para renderizar Reels", caminho_imagem=caminho_reels)
                print("      ⚠️ Reels: Ignorado (sem imagem).")
        except Exception as e:
            registrar_resultado_canal(item_id, "instagram_reels", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_reels)
            print(f"      ❌ Reels: Falha ({e})")

    return resultado


def main():
    load_env()
    env_delay = int(os.environ.get("DELAY_ENTRE_PRODUTOS") or os.environ.get("ZAPI_DELAY_MESSAGE") or 60)

    parser = argparse.ArgumentParser(description="Publicador automático multicanal para afiliados Shopee.")
    parser.add_argument("csv_path", nargs="?", default="produtos/teste.csv", help="Caminho do arquivo CSV (padrão: produtos/teste.csv)")
    parser.add_argument("--dry-run", action="store_true", help="Executa sem realizar publicações reais.")
    parser.add_argument("--delay", type=int, default=env_delay, help="Intervalo em segundos entre cada produto (padrão: 60s / 1 minuto).")
    parser.add_argument("--limit", type=int, default=None, help="Quantidade máxima de produtos a processar nesta execução.")
    parser.add_argument("--status", action="store_true", help="Exibe relatório consolidado de publicações do banco SQLite e sai.")
    parser.add_argument("--retry-failed", action="store_true", help="Reprocessa apenas produtos que possuem pendências ou falhas no banco SQLite.")
    args = parser.parse_args()

    if args.status:
        gerar_relatorio_terminal()
        return

    if args.retry_failed:
        print("🔄 Modo de Reprocessamento: Carregando produtos com falha/pendência do SQLite...")
        produtos = obter_produtos_para_reprocessamento()
        print(f"🎯 Total de produtos para reprocessar: {len(produtos)}")
    else:
        csv_file = Path(args.csv_path)
        if not csv_file.is_absolute():
            csv_file = ROOT / csv_file
        print(f"📂 Lendo catálogo: {csv_file}")
        produtos_lidos = parse_csv(csv_file)
        
        # Regra obrigatória: ignora a inclusão/processamento caso o Item ID já exista no banco
        produtos = []
        duplicados_ignorados = 0
        ids_vistos = set()
        for p in produtos_lidos:
            pid = str(p.get("item_id", "")).strip()
            if not pid or pid in ids_vistos or obter_produto(pid):
                duplicados_ignorados += 1
            else:
                ids_vistos.add(pid)
                produtos.append(p)

        if duplicados_ignorados > 0:
            print(f"⏩ {duplicados_ignorados} produto(s) ignorado(s) por já existirem no banco de dados.")

        if args.limit:
            produtos = produtos[:args.limit]
        print(f"🎯 Total de novos produtos a processar: {len(produtos)}")

    if not produtos:
        print("Nenhum produto a processar.")
        return

    fb_client = FacebookPageClient()
    ig_client = InstagramClient()
    wa_client = ZApiClient()

    for i, produto in enumerate(produtos, start=1):
        publicar_produto(produto, fb_client, ig_client, wa_client, dry_run=args.dry_run)
        if i < len(produtos):
            tempo_msg = f"{args.delay // 60} minuto(s)" if args.delay % 60 == 0 else f"{args.delay} segundos"
            print(f"⏳ Aguardando {tempo_msg} antes do próximo produto...")
            time.sleep(args.delay)

    print("\n🏁 Processo de publicação finalizado.")


if __name__ == "__main__":
    main()
