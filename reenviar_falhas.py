#!/usr/bin/env python3
"""Script específico para reprocessar e reenviar produtos com pendências ou falhas.

Consulta o banco SQLite (db/publicacoes.db) e tenta enviar cirurgicamente
apenas os canais (WhatsApp, Facebook, Stories, Post, Reels) que ainda não
foram concluídos com SUCESSO.
"""
import argparse
import datetime
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
from instagran.tratarParaInstagran import gerar_todas_imagens
from db.controle import (
    inicializar_banco,
    obter_produtos_para_reprocessamento,
    obter_produto,
    obter_status_canais,
    registrar_resultado_canal,
    atualizar_codigo_artes,
    gerar_relatorio_terminal,
    CANAIS_OBRIGATORIOS,
    DB_PATH,
)


def format_caption(item_name: str, offer_link: str, price: str | None = None) -> str:
    """Gera legenda padrão para publicações nas redes sociais."""
    preco_txt = f"\n💰 Por apenas R$ {price}" if price else ""
    return (
        f"🔥 *{item_name}*{preco_txt}\n\n"
        f"Garanta o seu com desconto no link oficial da Shopee:\n"
        f"👉 {offer_link}"
    )


def localizar_artes_produto(item_id: str, pasta_artes_registrada: str | None = None) -> dict[str, Path]:
    """Localiza as artes já geradas no disco para evitar renderizações desnecessárias."""
    artes = {}
    pastas_candidatas = []

    if pasta_artes_registrada:
        pastas_candidatas.append(Path(pasta_artes_registrada))

    # Busca em db/img/*/<item_id>/
    base_db_img = ROOT / "db" / "img"
    if base_db_img.exists():
        for d in sorted(base_db_img.glob(f"*/{item_id}"), reverse=True):
            if d.is_dir() and d not in pastas_candidatas:
                pastas_candidatas.append(d)

    # Fallback legado: instagran/img/
    legado_dir = ROOT / "instagran" / "img"
    if legado_dir.exists():
        pastas_candidatas.append(legado_dir)

    for pasta in pastas_candidatas:
        if not pasta.exists():
            continue

        stories = pasta / f"{item_id}_stories.png"
        post = pasta / f"{item_id}_post.png"
        reeals = pasta / f"{item_id}_reeals.png"
        reels_alias = pasta / f"{item_id}_reels.png"

        if stories.exists():
            artes["stories"] = stories
        if post.exists():
            artes["post"] = post
        if reeals.exists():
            artes["reeals"] = reeals
            artes["reels"] = reeals
        elif reels_alias.exists():
            artes["reeals"] = reels_alias
            artes["reels"] = reels_alias

        if "stories" in artes and "post" in artes and "reeals" in artes:
            artes["pasta"] = pasta
            artes["codigo"] = item_id
            return artes

    return artes


def reenviar_produto_pendente(
    produto: dict,
    fb_client: FacebookPageClient | None,
    ig_client: InstagramClient | None,
    wa_client: ZApiClient | None,
    dry_run: bool = False,
) -> dict:
    """Tenta reenviar cirurgicamente os canais que falharam ou estão pendentes para um produto."""
    item_id = str(produto["item_id"])
    item_name = produto.get("item_name", "Produto Shopee")
    offer_link = produto.get("offer_link", "")
    product_link = produto.get("product_link", "")
    price = produto.get("price")
    pasta_artes = produto.get("pasta_artes")

    status_canais = obter_status_canais(item_id)
    pendentes = [c for c in CANAIS_OBRIGATORIOS if status_canais.get(c) != "SUCESSO"]

    if not pendentes:
        print(f"\n✅ [JÁ CONCLUÍDO] {item_name} (ID: {item_id})")
        print("   Todos os 5 canais já constam com SUCESSO no banco.")
        return {"item_id": item_id, "status": "CONCLUIDO"}

    print(f"\n==========================================")
    print(f"🔄 Reenviando pendências: {item_name} (ID: {item_id})")
    print(f"📋 Canais a processar ({len(pendentes)}): {', '.join(pendentes)}")

    # 1. Localização ou busca das imagens
    artes = localizar_artes_produto(item_id, pasta_artes)
    primary_image = produto.get("image_url")
    if not primary_image and product_link:
        images = fetch_product_images(product_link, max_images=2, item_id=item_id)
        if images:
            primary_image = images[0]
            try:
                from db.controle import atualizar_imagem_produto
                atualizar_imagem_produto(item_id, primary_image)
            except Exception:
                pass

    # Verifica se as artes existentes possuem a foto original em cache
    pasta_existente = artes.get("pasta")
    tem_foto_original = pasta_existente and (pasta_existente / "original.jpg").exists()

    # Se faltar canal do Instagram e as artes não existirem ou estiverem sem a foto original
    precisa_instagram = any(c in pendentes for c in ["instagram_stories", "instagram_post", "instagram_reels"])
    artes_incompletas = not artes.get("stories") or not artes.get("post") or not artes.get("reeals") or (not tem_foto_original and primary_image)

    if precisa_instagram and artes_incompletas:
        if primary_image:
            print("🎨 Gerando novas artes para Instagram com template e foto oficial do produto...")
            try:
                clean_price = price.replace("R$", "").strip() if price else "OFERTA"
                artes = gerar_todas_imagens({
                    "item_id": item_id,
                    "title": item_name,
                    "image_url": primary_image,
                    "price": clean_price,
                    "url": offer_link,
                })
                atualizar_codigo_artes(item_id, artes.get("codigo"), pasta_artes=str(artes.get("pasta")))
                print(f"   ✅ Novas artes geradas em: {artes.get('pasta')}")
            except Exception as e:
                print(f"   ⚠️ Não foi possível gerar as artes: {e}")
        else:
            print("   ⚠️ Sem imagem base para gerar artes do Instagram.")


    caption = format_caption(item_name, offer_link, price)
    resultado = {"item_id": item_id, "canais": {}}

    if dry_run:
        print("[DRY-RUN] Simulação ativa. Nenhuma requisição externa realizada.")
        for canal in pendentes:
            print(f"   🔍 [DRY-RUN] Seria reenviado: {canal}")
        return resultado

    story_png = artes.get("stories")
    post_png = artes.get("post")
    reels_png = artes.get("reeals") or artes.get("reels")
    pasta_existente = artes.get("pasta")
    original_img_path = (pasta_existente / "original.jpg") if (pasta_existente and (pasta_existente / "original.jpg").exists()) else None

    # 1. WhatsApp
    if "whatsapp" in pendentes and wa_client:
        print("💬 [1/5] Tentando reenviar WhatsApp...")
        caminho_wa = str(post_png) if (post_png and post_png.exists()) else (str(original_img_path) if original_img_path else (primary_image if primary_image else None))
        try:
            res_wa = wa_client.send_to_group(caption, image_url=caminho_wa)
            msg_id = res_wa.get("messageId") or res_wa.get("zaapId")
            resultado["canais"]["whatsapp"] = "SUCESSO"
            registrar_resultado_canal(item_id, "whatsapp", "SUCESSO", id_externo=msg_id, caminho_imagem=caminho_wa)
            print(f"   ✅ WhatsApp: Sucesso (ID: {msg_id})")
        except Exception as e:
            resultado["canais"]["whatsapp"] = "FALHA"
            registrar_resultado_canal(item_id, "whatsapp", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_wa)
            print(f"   ❌ WhatsApp: Falha ({e})")
    elif "whatsapp" not in pendentes:
        print("💬 [1/5] WhatsApp: Já concluído. Pulando.")

    # 2. Facebook
    if "facebook" in pendentes and fb_client:
        print("📘 [2/5] Tentando reenviar Facebook...")
        caminho_fb = primary_image if primary_image else None
        try:
            if primary_image:
                res_fb = fb_client.publish_photo(primary_image, caption)
            else:
                res_fb = fb_client.publish_post(caption, link=offer_link)
            post_id = res_fb.get("post_id") or res_fb.get("id")
            resultado["canais"]["facebook"] = "SUCESSO"
            registrar_resultado_canal(item_id, "facebook", "SUCESSO", id_externo=post_id, caminho_imagem=caminho_fb)
            print(f"   ✅ Facebook: Sucesso (ID: {post_id})")
        except Exception as e:
            resultado["canais"]["facebook"] = "FALHA"
            registrar_resultado_canal(item_id, "facebook", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_fb)
            print(f"   ❌ Facebook: Falha ({e})")
    elif "facebook" not in pendentes:
        print("📘 [2/5] Facebook: Já concluído. Pulando.")

    story_png = artes.get("stories")
    post_png = artes.get("post")
    reels_png = artes.get("reeals") or artes.get("reels")

    # 3. Instagram Stories
    if "instagram_stories" in pendentes and ig_client and fb_client:
        print("📲 [3/5] Tentando reenviar Stories...")
        caminho_story = str(story_png) if (story_png and story_png.exists()) else (primary_image if primary_image else None)
        try:
            if story_png and story_png.exists():
                story_cdn_url = fb_client.upload_photo_to_cdn(story_png)
                res_story = ig_client.publish_story(story_cdn_url)
                story_id = res_story.get("id")
                resultado["canais"]["instagram_stories"] = "SUCESSO"
                registrar_resultado_canal(item_id, "instagram_stories", "SUCESSO", id_externo=story_id, caminho_imagem=caminho_story)
                print(f"   ✅ Stories: Sucesso (ID: {story_id})")
            elif primary_image:
                res_story = ig_client.publish_story(primary_image)
                story_id = res_story.get("id")
                resultado["canais"]["instagram_stories"] = "SUCESSO"
                registrar_resultado_canal(item_id, "instagram_stories", "SUCESSO", id_externo=story_id, caminho_imagem=caminho_story)
                print(f"   ✅ Stories: Sucesso com imagem original (ID: {story_id})")
            else:
                resultado["canais"]["instagram_stories"] = "FALHA"
                registrar_resultado_canal(item_id, "instagram_stories", "FALHA", mensagem_erro="Imagem ausente para renderizar template de Stories", caminho_imagem=caminho_story)
                print("   ⚠️ Stories: Não foi possível enviar (sem imagem).")
        except Exception as e:
            resultado["canais"]["instagram_stories"] = "FALHA"
            registrar_resultado_canal(item_id, "instagram_stories", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_story)
            print(f"   ❌ Stories: Falha ({e})")
    elif "instagram_stories" not in pendentes:
        print("📲 [3/5] Stories: Já concluído. Pulando.")

    # 4. Instagram Post no Feed
    if "instagram_post" in pendentes and ig_client and fb_client:
        print("🖼️  [4/5] Tentando reenviar Post no Feed...")
        caminho_post = str(post_png) if (post_png and post_png.exists()) else (primary_image if primary_image else None)
        try:
            if post_png and post_png.exists():
                post_cdn_url = fb_client.upload_photo_to_cdn(post_png)
                res_post = ig_client.publish_photo(post_cdn_url, caption)
                post_id = res_post.get("id")
                resultado["canais"]["instagram_post"] = "SUCESSO"
                registrar_resultado_canal(item_id, "instagram_post", "SUCESSO", id_externo=post_id, caminho_imagem=caminho_post)
                print(f"   ✅ Post Feed: Sucesso (ID: {post_id})")
            elif primary_image:
                res_post = ig_client.publish_photo(primary_image, caption)
                post_id = res_post.get("id")
                resultado["canais"]["instagram_post"] = "SUCESSO"
                registrar_resultado_canal(item_id, "instagram_post", "SUCESSO", id_externo=post_id, caminho_imagem=caminho_post)
                print(f"   ✅ Post Feed: Sucesso com imagem original (ID: {post_id})")
            else:
                resultado["canais"]["instagram_post"] = "FALHA"
                registrar_resultado_canal(item_id, "instagram_post", "FALHA", mensagem_erro="Imagem ausente para renderizar template de Post Feed", caminho_imagem=caminho_post)
                print("   ⚠️ Post Feed: Não foi possível enviar (sem imagem).")
        except Exception as e:
            resultado["canais"]["instagram_post"] = "FALHA"
            registrar_resultado_canal(item_id, "instagram_post", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_post)
            print(f"   ❌ Post Feed: Falha ({e})")
    elif "instagram_post" not in pendentes:
        print("🖼️  [4/5] Post Feed: Já concluído. Pulando.")

    # 5. Instagram Reels
    if "instagram_reels" in pendentes and ig_client:
        print("🎬 [5/5] Tentando reenviar Reels...")
        target_reels_img = reels_png if (reels_png and reels_png.exists()) else story_png
        video_reels_mp4 = target_reels_img.with_suffix(".mp4") if target_reels_img else None
        caminho_reels = str(video_reels_mp4) if (video_reels_mp4 and video_reels_mp4.exists()) else (str(target_reels_img) if target_reels_img else None)
        try:
            if target_reels_img and target_reels_img.exists():
                res_reels = ig_client.publish_reel_from_image(target_reels_img, caption)
                reels_id = res_reels.get("id")
                resultado["canais"]["instagram_reels"] = "SUCESSO"
                if video_reels_mp4 and video_reels_mp4.exists():
                    caminho_reels = str(video_reels_mp4)
                registrar_resultado_canal(item_id, "instagram_reels", "SUCESSO", id_externo=reels_id, caminho_imagem=caminho_reels)
                print(f"   ✅ Reels: Sucesso (ID: {reels_id})")
            else:
                resultado["canais"]["instagram_reels"] = "FALHA"
                registrar_resultado_canal(item_id, "instagram_reels", "FALHA", mensagem_erro="Imagem compatível ausente para renderizar Reels", caminho_imagem=caminho_reels)
                print("   ⚠️ Reels: Não foi possível enviar (sem imagem compatível).")
        except Exception as e:
            resultado["canais"]["instagram_reels"] = "FALHA"
            registrar_resultado_canal(item_id, "instagram_reels", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_reels)
            print(f"   ❌ Reels: Falha ({e})")
    elif "instagram_reels" not in pendentes:
        print("🎬 [5/5] Reels: Já concluído. Pulando.")

    return resultado


def main():
    load_env()
    env_delay = int(os.environ.get("DELAY_ENTRE_PRODUTOS") or os.environ.get("ZAPI_DELAY_MESSAGE") or 60)

    parser = argparse.ArgumentParser(description="Script para ler produtos não enviados ou com falha e tentar reenviá-los.")
    parser.add_argument("--item-id", default=None, help="Processa exclusivamente o Item Id informado.")
    parser.add_argument("--dry-run", action="store_true", help="Simula o reenvio sem efetuar chamadas externas.")
    parser.add_argument("--delay", type=int, default=env_delay, help="Intervalo em segundos entre cada produto reprocessado (padrão: 60s).")
    parser.add_argument("--limit", type=int, default=None, help="Quantidade máxima de produtos a reprocessar.")
    parser.add_argument("--status", action="store_true", help="Exibe apenas o relatório de status atual do banco e sai.")
    args = parser.parse_args()

    inicializar_banco()

    if args.status:
        gerar_relatorio_terminal()
        return

    # 1. Carrega os produtos com pendências
    if args.item_id:
        prod = obter_produto(args.item_id)
        if not prod:
            print(f"❌ Produto com Item Id '{args.item_id}' não encontrado na base de dados.")
            sys.exit(1)
        fila = [prod]
    else:
        fila = obter_produtos_para_reprocessamento()

    if not fila:
        print("🎉 Nenhum produto com pendência ou falha encontrado!")
        print("   Todas as publicações registradas estão 100% concluídas.")
        gerar_relatorio_terminal()
        return

    total = len(fila)
    if args.limit and args.limit > 0:
        fila = fila[:args.limit]

    print("=======================================================")
    print("🚀 INICIANDO REENVIO DE PUBLICAÇÕES PENDENTES")
    print("=======================================================")
    print(f"Total de produtos na fila: {len(fila)} (de {total} pendentes)")
    print(f"Modo de execução:          {'DRY-RUN (Simulação)' if args.dry_run else 'REAL'}")
    print(f"Intervalo entre produtos:  {args.delay} segundos")
    print("=======================================================")

    # 2. Inicialização dos clientes de redes sociais apenas se não for dry-run
    fb_client = None
    ig_client = None
    wa_client = None

    if not args.dry_run:
        print("\n🔑 Inicializando credenciais dos canais...")
        try:
            fb_client = FacebookPageClient()
            print("   ✅ Facebook Page API conectada.")
        except Exception as e:
            print(f"   ⚠️ Falha ao autenticar Facebook Page: {e}")

        try:
            ig_client = InstagramClient()
            print("   ✅ Instagram Graph API conectada.")
        except Exception as e:
            print(f"   ⚠️ Falha ao autenticar Instagram: {e}")

        try:
            wa_client = ZApiClient()
            print("   ✅ WhatsApp Z-API conectada.")
        except Exception as e:
            print(f"   ⚠️ Falha ao autenticar WhatsApp: {e}")

    # 3. Execução da fila de reenvio
    for idx, produto in enumerate(fila, start=1):
        print(f"\n[{idx}/{len(fila)}] Iniciando produto ID: {produto.get('item_id')}")
        reenviar_produto_pendente(produto, fb_client, ig_client, wa_client, dry_run=args.dry_run)

        if idx < len(fila):
            print(f"\n⏳ Aguardando {args.delay} segundos antes do próximo produto...")
            time.sleep(args.delay)

    # 4. Relatório final consolidado
    print("\n🏁 Processamento de reenvios finalizado.")
    gerar_relatorio_terminal()


if __name__ == "__main__":
    main()
