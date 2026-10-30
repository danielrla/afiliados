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
try:
    from produtos.reader import fetch_product_images
except ImportError:
    def fetch_product_images(*args, **kwargs) -> list[str]:
        return []
from instagran.tratarParaInstagran import gerar_todas_imagens
from db.controle import (
    inicializar_banco,
    obter_produtos_para_reprocessamento,
    obter_produto,
    obter_status_canais,
    marcar_canal_enviando,
    registrar_resultado_canal,
    atualizar_codigo_artes,
    gerar_relatorio_terminal,
    CANAIS_OBRIGATORIOS,
    DB_PATH,
)


def format_caption(item_name: str, offer_link: str, price: str | None = None) -> str:
    """Gera legenda padrão para publicações nas redes sociais adaptada à loja de origem."""
    preco_txt = f"\n💰 Por apenas R$ {price}" if price and str(price) not in ("0", "0.0", "--") else ""
    link_lower = (offer_link or "").lower()
    if "meli.la" in link_lower or "mercadolivre" in link_lower:
        loja_txt = "no link oficial do Mercado Livre"
    elif "shopee" in link_lower or "shp.ee" in link_lower:
        loja_txt = "no link oficial da Shopee"
    else:
        loja_txt = "no link oficial"
    return (
        f"🔥 *{item_name}*{preco_txt}\n\n"
        f"Garanta o seu com desconto {loja_txt}:\n"
        f"👉 {offer_link}"
    )


def localizar_artes_produto(item_id: str, pasta_artes_registrada: str | None = None) -> dict[str, Path]:
    """Localiza as artes já geradas no disco validando se são mais recentes que instagran/templates/."""
    from db.controle import localizar_artes_produto as _localizar_artes_db
    return _localizar_artes_db(item_id, pasta_artes_registrada)


def reenviar_produto_pendente(
    produto: dict,
    fb_client: FacebookPageClient | None,
    ig_client: InstagramClient | None,
    wa_client: ZApiClient | None,
    dry_run: bool = False,
    on_etapa=None,
) -> dict:
    """Tenta reenviar cirurgicamente os canais que falharam ou estão pendentes para um produto."""
    item_id = str(produto["item_id"])
    item_name = produto.get("item_name", "Produto")
    offer_link = produto.get("offer_link", "")
    product_link = produto.get("product_link", "")
    price = produto.get("price")
    pasta_artes = produto.get("pasta_artes")

    def _notificar_etapa(canal: str, descricao: str, marcar_db: bool = True) -> None:
        if marcar_db and not dry_run and canal in CANAIS_OBRIGATORIOS:
            try:
                marcar_canal_enviando(item_id, canal)
            except Exception:
                pass
        if callable(on_etapa):
            try:
                on_etapa(item_id, canal, descricao)
            except Exception:
                pass

    status_canais = obter_status_canais(item_id)
    pendentes = [c for c in CANAIS_OBRIGATORIOS if status_canais.get(c) != "SUCESSO"]

    if not pendentes:
        print(f"\n✅ [JÁ CONCLUÍDO] {item_name} (ID: {item_id})")
        print("   Todos os 6 canais já constam com SUCESSO no banco.")
        return {"item_id": item_id, "status": "CONCLUIDO"}

    print(f"\n==========================================")
    print(f"🔄 Reenviando pendências: {item_name} (ID: {item_id})")
    print(f"📋 Canais a processar ({len(pendentes)}): {', '.join(pendentes)}")

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

    # Geração de links rastreados por canal via Shopee Affiliate API (apenas para links da Shopee)
    origin_link = product_link or offer_link
    eh_link_shopee = "shopee" in (origin_link or "").lower() or "shp.ee" in (origin_link or "").lower()
    shopee_client = None
    if eh_link_shopee:
        try:
            from shopee.client import ShopeeAffiliateClient
            shopee_client = ShopeeAffiliateClient()
        except Exception:
            pass

    link_wa = (shopee_client.gerar_link_canal(origin_link, "whatsapp") if shopee_client else None) or offer_link
    link_fb = (shopee_client.gerar_link_canal(origin_link, "facebook") if shopee_client else None) or offer_link
    link_fb_reels = (shopee_client.gerar_link_canal(origin_link, "facebook_reels") if shopee_client else None) or offer_link
    link_stories = (shopee_client.gerar_link_canal(origin_link, "instagram_stories") if shopee_client else None) or offer_link
    link_post = (shopee_client.gerar_link_canal(origin_link, "instagram_post") if shopee_client else None) or offer_link
    link_reels = (shopee_client.gerar_link_canal(origin_link, "instagram_reels") if shopee_client else None) or offer_link

    caption_wa = format_caption(item_name, link_wa, price)
    caption_fb = format_caption(item_name, link_fb, price)
    caption_fb_reels = format_caption(item_name, link_fb_reels, price)
    caption_post = format_caption(item_name, link_post, price)
    caption_reels = format_caption(item_name, link_reels, price)
    caption = caption_wa

    resultado = {"item_id": item_id, "canais": {}}

    if dry_run:
        print("[DRY-RUN] Simulação ativa. Nenhuma requisição externa realizada.")
        for canal in pendentes:
            print(f"   🔍 [DRY-RUN] Seria reenviado: {canal}")
        return resultado

    # 1. WhatsApp - Regra de negócio: envia exclusivamente a imagem original do link do produto, sem aplicar template
    if "whatsapp" in pendentes and wa_client:
        _notificar_etapa("whatsapp", "Enviando para o grupo do WhatsApp (1/6)...")
        print("💬 [1/6] Tentando reenviar WhatsApp com imagem original do link (sem template)...")
        caminho_wa = primary_image if primary_image else None
        try:
            res_wa = wa_client.send_to_group(caption_wa, image_url=caminho_wa)
            msg_id = res_wa.get("messageId") or res_wa.get("zaapId")
            resultado["canais"]["whatsapp"] = "SUCESSO"
            registrar_resultado_canal(item_id, "whatsapp", "SUCESSO", id_externo=msg_id, caminho_imagem=caminho_wa, link_rastreado=link_wa)
            print(f"   ✅ WhatsApp: Sucesso (ID: {msg_id})")
        except Exception as e:
            resultado["canais"]["whatsapp"] = "FALHA"
            registrar_resultado_canal(item_id, "whatsapp", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_wa, link_rastreado=link_wa)
            print(f"   ❌ WhatsApp: Falha ({e})")
    elif "whatsapp" not in pendentes:
        print("💬 [1/6] WhatsApp: Já concluído. Pulando.")

    # 2. Facebook (Post no Feed) - Regra de negócio: envia exclusivamente a imagem do link do produto, sem aplicar template
    if "facebook" in pendentes and fb_client:
        _notificar_etapa("facebook", "Publicando foto no Feed do Facebook (2/6)...")
        print("📘 [2/6] Tentando reenviar Facebook com imagem original do link (sem template)...")
        caminho_fb = primary_image if primary_image else None
        try:
            if caminho_fb:
                res_fb = fb_client.publish_photo(caminho_fb, caption_fb)
            else:
                res_fb = fb_client.publish_post(caption_fb, link=link_fb)
            post_id = res_fb.get("post_id") or res_fb.get("id")
            resultado["canais"]["facebook"] = "SUCESSO"
            registrar_resultado_canal(item_id, "facebook", "SUCESSO", id_externo=post_id, caminho_imagem=caminho_fb, link_rastreado=link_fb)
            print(f"   ✅ Facebook: Sucesso (ID: {post_id})")
        except Exception as e:
            resultado["canais"]["facebook"] = "FALHA"
            registrar_resultado_canal(item_id, "facebook", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_fb, link_rastreado=link_fb)
            print(f"   ❌ Facebook: Falha ({e})")
    elif "facebook" not in pendentes:
        print("📘 [2/6] Facebook: Já concluído. Pulando.")

    # Processamento de artes de templates (instagran/templates) para os canais que usam template
    precisa_templates = any(
        c in pendentes
        for c in ["facebook_reels", "instagram_stories", "instagram_post", "instagram_reels"]
    )
    artes = {}
    if precisa_templates:
        _notificar_etapa("templates", "Renderizando templates Linkolândia (Stories, Post e Reels)...", marcar_db=False)
        print("📸 Processando artes de templates (instagran/templates) para redes sociais...")
        artes = localizar_artes_produto(item_id, pasta_artes)
        pasta_existente = artes.get("pasta")
        tem_foto_original = pasta_existente and (pasta_existente / "original.jpg").exists()
        artes_incompletas = (
            not artes.get("stories")
            or not artes.get("post")
            or not artes.get("reeals")
            or not artes.get("reels_mp4")
            or (not tem_foto_original and primary_image)
        )
        if artes_incompletas:
            if primary_image:
                print("🎨 Gerando novas artes com templates Linkolândia (instagran/templates)...")
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
                print("   ⚠️ Sem imagem base para gerar artes das templates.")

    story_png = artes.get("stories")
    post_png = artes.get("post")
    reels_png = artes.get("reeals") or artes.get("reels")

    # 3. Facebook Reels
    if "facebook_reels" in pendentes and fb_client:
        _notificar_etapa("facebook_reels", "Publicando vídeo no Facebook Reels (3/6)...")
        print("🎬 [3/6] Tentando reenviar Facebook Reels...")
        target_reels_img = reels_png if (reels_png and reels_png.exists()) else story_png
        video_reels_mp4 = target_reels_img.with_suffix(".mp4") if target_reels_img else None
        caminho_fb_reels = str(video_reels_mp4) if (video_reels_mp4 and video_reels_mp4.exists()) else (str(target_reels_img) if target_reels_img else None)
        try:
            if video_reels_mp4 and video_reels_mp4.exists():
                res_fb_reels = fb_client.publish_reel(video_reels_mp4, caption_fb_reels)
                reel_id = res_fb_reels.get("video_id")
                resultado["canais"]["facebook_reels"] = "SUCESSO"
                registrar_resultado_canal(item_id, "facebook_reels", "SUCESSO", id_externo=reel_id, caminho_imagem=str(video_reels_mp4), link_rastreado=link_fb_reels)
                print(f"   ✅ Facebook Reels: Sucesso (ID: {reel_id})")
            elif target_reels_img and target_reels_img.exists():
                res_fb_reels = fb_client.publish_reel_from_image(target_reels_img, caption_fb_reels)
                reel_id = res_fb_reels.get("video_id")
                resultado["canais"]["facebook_reels"] = "SUCESSO"
                caminho_salvo = str(target_reels_img.with_suffix(".mp4")) if target_reels_img.with_suffix(".mp4").exists() else str(target_reels_img)
                registrar_resultado_canal(item_id, "facebook_reels", "SUCESSO", id_externo=reel_id, caminho_imagem=caminho_salvo, link_rastreado=link_fb_reels)
                print(f"   ✅ Facebook Reels: Sucesso gerado via imagem (ID: {reel_id})")
            else:
                resultado["canais"]["facebook_reels"] = "FALHA"
                registrar_resultado_canal(item_id, "facebook_reels", "FALHA", mensagem_erro="Mídia compatível ausente para Facebook Reels", caminho_imagem=caminho_fb_reels, link_rastreado=link_fb_reels)
                print("   ⚠️ Facebook Reels: Não foi possível enviar (sem mídia compatível).")
        except Exception as e:
            resultado["canais"]["facebook_reels"] = "FALHA"
            registrar_resultado_canal(item_id, "facebook_reels", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_fb_reels, link_rastreado=link_fb_reels)
            print(f"   ❌ Facebook Reels: Falha ({e})")
    elif "facebook_reels" not in pendentes:
        print("🎬 [3/6] Facebook Reels: Já concluído. Pulando.")

    # 4. Instagram Stories
    if "instagram_stories" in pendentes and ig_client and fb_client:
        _notificar_etapa("instagram_stories", "Publicando arte nos Stories do Instagram (4/6)...")
        print("📲 [4/6] Tentando reenviar Stories...")
        caminho_story = str(story_png) if (story_png and story_png.exists()) else (primary_image if primary_image else None)
        try:
            if story_png and story_png.exists():
                story_cdn_url = fb_client.upload_photo_to_cdn(story_png)
                res_story = ig_client.publish_story(story_cdn_url)
                story_id = res_story.get("id")
                resultado["canais"]["instagram_stories"] = "SUCESSO"
                registrar_resultado_canal(item_id, "instagram_stories", "SUCESSO", id_externo=story_id, caminho_imagem=caminho_story, link_rastreado=link_stories)
                print(f"   ✅ Stories: Sucesso (ID: {story_id})")
            elif primary_image:
                res_story = ig_client.publish_story(primary_image)
                story_id = res_story.get("id")
                resultado["canais"]["instagram_stories"] = "SUCESSO"
                registrar_resultado_canal(item_id, "instagram_stories", "SUCESSO", id_externo=story_id, caminho_imagem=caminho_story, link_rastreado=link_stories)
                print(f"   ✅ Stories: Sucesso com imagem original (ID: {story_id})")
            else:
                resultado["canais"]["instagram_stories"] = "FALHA"
                registrar_resultado_canal(item_id, "instagram_stories", "FALHA", mensagem_erro="Imagem ausente para renderizar template de Stories", caminho_imagem=caminho_story, link_rastreado=link_stories)
                print("   ⚠️ Stories: Não foi possível enviar (sem imagem).")
        except Exception as e:
            resultado["canais"]["instagram_stories"] = "FALHA"
            registrar_resultado_canal(item_id, "instagram_stories", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_story, link_rastreado=link_stories)
            print(f"   ❌ Stories: Falha ({e})")
    elif "instagram_stories" not in pendentes:
        print("📲 [4/6] Stories: Já concluído. Pulando.")

    # 5. Instagram Post no Feed
    if "instagram_post" in pendentes and ig_client and fb_client:
        _notificar_etapa("instagram_post", "Publicando arte no Feed do Instagram (5/6)...")
        print("🖼️  [5/6] Tentando reenviar Post no Feed...")
        caminho_post = str(post_png) if (post_png and post_png.exists()) else (primary_image if primary_image else None)
        try:
            if post_png and post_png.exists():
                post_cdn_url = fb_client.upload_photo_to_cdn(post_png)
                res_post = ig_client.publish_photo(post_cdn_url, caption_post)
                post_id = res_post.get("id")
                resultado["canais"]["instagram_post"] = "SUCESSO"
                registrar_resultado_canal(item_id, "instagram_post", "SUCESSO", id_externo=post_id, caminho_imagem=caminho_post, link_rastreado=link_post)
                print(f"   ✅ Post Feed: Sucesso (ID: {post_id})")
            elif primary_image:
                res_post = ig_client.publish_photo(primary_image, caption_post)
                post_id = res_post.get("id")
                resultado["canais"]["instagram_post"] = "SUCESSO"
                registrar_resultado_canal(item_id, "instagram_post", "SUCESSO", id_externo=post_id, caminho_imagem=caminho_post, link_rastreado=link_post)
                print(f"   ✅ Post Feed: Sucesso com imagem original (ID: {post_id})")
            else:
                resultado["canais"]["instagram_post"] = "FALHA"
                registrar_resultado_canal(item_id, "instagram_post", "FALHA", mensagem_erro="Imagem ausente para renderizar template de Post Feed", caminho_imagem=caminho_post, link_rastreado=link_post)
                print("   ⚠️ Post Feed: Não foi possível enviar (sem imagem).")
        except Exception as e:
            resultado["canais"]["instagram_post"] = "FALHA"
            registrar_resultado_canal(item_id, "instagram_post", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_post, link_rastreado=link_post)
            print(f"   ❌ Post Feed: Falha ({e})")
    elif "instagram_post" not in pendentes:
        print("🖼️  [5/6] Post Feed: Já concluído. Pulando.")

    # 6. Instagram Reels
    if "instagram_reels" in pendentes and ig_client:
        _notificar_etapa("instagram_reels", "Publicando vídeo no Instagram Reels (6/6)...")
        print("🎬 [6/6] Tentando reenviar Reels...")
        target_reels_img = reels_png if (reels_png and reels_png.exists()) else story_png
        video_reels_mp4 = target_reels_img.with_suffix(".mp4") if target_reels_img else None
        caminho_reels = str(video_reels_mp4) if (video_reels_mp4 and video_reels_mp4.exists()) else (str(target_reels_img) if target_reels_img else None)
        try:
            if target_reels_img and target_reels_img.exists():
                res_reels = ig_client.publish_reel_from_image(target_reels_img, caption_reels)
                reels_id = res_reels.get("id")
                resultado["canais"]["instagram_reels"] = "SUCESSO"
                if video_reels_mp4 and video_reels_mp4.exists():
                    caminho_reels = str(video_reels_mp4)
                registrar_resultado_canal(item_id, "instagram_reels", "SUCESSO", id_externo=reels_id, caminho_imagem=caminho_reels, link_rastreado=link_reels)
                print(f"   ✅ Reels: Sucesso (ID: {reels_id})")
            else:
                resultado["canais"]["instagram_reels"] = "FALHA"
                registrar_resultado_canal(item_id, "instagram_reels", "FALHA", mensagem_erro="Imagem compatível ausente para Reels", caminho_imagem=caminho_reels, link_rastreado=link_reels)
                print("   ⚠️ Reels: Não foi possível enviar (sem imagem).")
        except Exception as e:
            resultado["canais"]["instagram_reels"] = "FALHA"
            registrar_resultado_canal(item_id, "instagram_reels", "FALHA", mensagem_erro=str(e), caminho_imagem=caminho_reels, link_rastreado=link_reels)
            print(f"   ❌ Reels: Falha ({e})")
    elif "instagram_reels" not in pendentes:
        print("🎬 [6/6] Reels: Já concluído. Pulando.")

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
