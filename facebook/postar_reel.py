"""Script CLI para publicação de Reels em Páginas do Facebook via Meta Graph API."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shopee.client import load_env
from facebook.client import FacebookPageClient


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Publica um vídeo local como Reel na Página do Facebook.")
    parser.add_argument("--video", "-v", required=True, help="Caminho do arquivo de vídeo .mp4 ou imagem vertical.")
    parser.add_argument("--caption", "-c", default="Oferta exclusiva! Confira o link nos comentários. #shopee #dicas", help="Legenda do Reel.")
    parser.add_argument("--link", "-l", default=None, help="Link rastreado para anexar à legenda.")
    args = parser.parse_args()

    caminho = Path(args.video)
    if not caminho.is_absolute():
        caminho = ROOT / caminho

    if not caminho.exists():
        print(f"❌ Arquivo não encontrado: {caminho}")
        sys.exit(1)

    caption = args.caption
    if args.link:
        caption = f"{caption}\n\n👉 Compre aqui: {args.link}"

    client = FacebookPageClient()
    print(f"🎬 Iniciando publicação de Reel na Página '{client.page_id}'...")
    print(f"📁 Arquivo de origem: {caminho}")
    print(f"📝 Legenda: {caption[:80]}...")

    try:
        if caminho.suffix.lower() == ".mp4":
            res = client.publish_reel(caminho, caption)
        else:
            print("🎨 Arquivo de imagem detectado, convertendo em MP4 com FFmpeg...")
            res = client.publish_reel_from_image(caminho, caption)

        video_id = res.get("video_id")
        print("\n✅ [SUCESSO] Reel publicado com sucesso!")
        print(f"🆔 Video ID: {video_id}")
        print(f"📊 Detalhes: {json.dumps(res.get('details'), ensure_ascii=False)}")
        print(f"🔗 URL estimada: https://www.facebook.com/reel/{video_id}")

    except Exception as e:
        print(f"\n❌ [FALHA] Erro ao publicar Reel no Facebook: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
