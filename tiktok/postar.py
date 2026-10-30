"""Script para teste e publicação de vídeo no TikTok utilizando a Content Posting API v2."""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shopee.client import load_env
from tiktok.client import TikTokClient


def main():
    parser = argparse.ArgumentParser(description="Publicar vídeo no TikTok via Content Posting API v2")
    parser.add_argument(
        "--video",
        default="db/img/2026-10-27/21598313618/21598313618_reeals.mp4",
        help="Caminho do arquivo de vídeo local MP4",
    )
    parser.add_argument(
        "--title",
        default="Achadinho Imperdível na Shopee! 🔥 Link na bio ou comentários #shopee #achadinhos #ofertas",
        help="Legenda do vídeo no TikTok",
    )
    parser.add_argument(
        "--privacy",
        default="PUBLIC_TO_EVERYONE",
        choices=["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY", "FOLLOWER_OF_CREATOR"],
        help="Nível de privacidade do post",
    )
    parser.add_argument(
        "--redirect-uri",
        default="https://localhost:8000/api/tiktok/callback",
        help="Redirect URI cadastrada no TikTok Developer Portal",
    )
    parser.add_argument(
        "--code",
        help="Authorization Code retornado pelo TikTok após login para troca por access_token",
    )
    parser.add_argument(
        "--access-token",
        help="Token de acesso direto (Bearer) do TikTok",
    )
    args = parser.parse_args()

    load_env()
    client = TikTokClient(access_token=args.access_token)

    # 1. Se foi fornecido um authorization code, realiza a troca por tokens
    if args.code:
        print("🔄 Trocando authorization code por tokens de acesso...")
        try:
            res_token = client.trocar_code_por_token(args.code, args.redirect_uri)
            print("✅ Token de usuário obtido com sucesso!")
            print(f"Tipo: {res_token.get('token_type')}")
            print(f"Expira em: {res_token.get('expires_in')} segundos")
            print(f"Escopos: {res_token.get('scope')}")
        except Exception as e:
            print(f"❌ Erro ao trocar code: {e}")
            sys.exit(1)

    # 2. Verifica se o access_token de usuário está disponível
    if not client.access_token:
        print("\n⚠️  TIKTOK_ACCESS_TOKEN de usuário não encontrado no .env.")
        print("A Content Posting API do TikTok exige autorização da conta via OAuth 2.0 (User Access Token) com os escopos 'video.publish' ou 'video.upload'.")
        print("\n👉 Para autorizar a sua conta, acerte a Redirect URI cadastrada no seu TikTok Developer Portal e acesse a URL abaixo:")
        url_auth = client.obter_url_autorizacao(redirect_uri=args.redirect_uri)
        print(f"\n{url_auth}\n")
        print("Após autorizar no navegador, o TikTok redirecionará para a sua redirect_uri com o parâmetro '?code=SEU_CODE'.")
        print(f"Em seguida, execute este script fornecendo o code:")
        print(f"python3 tiktok/postar.py --code <SEU_CODE> --redirect-uri {args.redirect_uri}")
        print("\nOu, se já gerou um access_token no TikTok Developer Console:")
        print("Adicione TIKTOK_ACCESS_TOKEN=seu_token no arquivo .env e execute novamente.")
        sys.exit(1)

    # 3. Executa a publicação do vídeo
    video_path = Path(args.video)
    if not video_path.is_absolute():
        video_path = ROOT / video_path

    print(f"\n🎬 Iniciando publicação no TikTok...")
    print(f"Arquivo: {video_path}")
    print(f"Tamanho: {video_path.stat().st_size} bytes")
    print(f"Título: {args.title}")
    print(f"Privacidade: {args.privacy}")

    try:
        resultado = client.publicar_video(
            video_path=video_path,
            title=args.title,
            privacy_level=args.privacy,
            aguardar_conclusao=True,
        )
        print("\n🎉 VÍDEO PUBLICADO COM SUCESSO NO TIKTOK!")
        print(f"Publish ID: {resultado.get('publish_id')}")
        print(f"Status: {resultado.get('status')}")
    except Exception as e:
        print(f"\n❌ Falha na publicação no TikTok: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
