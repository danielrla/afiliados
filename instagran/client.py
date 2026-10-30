"""Cliente da Instagram Graph API para publicação de fotos e stories, apenas stdlib."""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shopee.client import load_env  # noqa: E402

GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v23.0")
BASE_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


class InstagramClient:
    def __init__(self, account_id: str | None = None, access_token: str | None = None):
        load_env()
        self.access_token = access_token or os.environ.get("META_PAGE_TOKEN") or os.environ.get("META_USER_TOKEN")
        if not self.access_token:
            raise RuntimeError("Token da Meta ausente no .env")

        resolved_id = account_id or os.environ.get("INSTAGRAM_ACCOUNT_ID")
        if not resolved_id:
            resolved_id = self._descobrir_conta_instagram()

        if not resolved_id:
            raise RuntimeError(
                "INSTAGRAM_ACCOUNT_ID ausente no ambiente e nenhuma conta Instagram Business vinculada "
                "à Página do Facebook no Meta Business Suite."
            )
        self.account_id = str(resolved_id).strip()

    def _descobrir_conta_instagram(self) -> str | None:
        """Tenta descobrir o ID do Instagram Business vinculado à Página do Facebook via Graph API."""
        if not self.access_token:
            return None
        page_id = os.environ.get("META_PAGE_ID")
        if page_id:
            try:
                data = urllib.parse.urlencode({
                    "fields": "instagram_business_account,connected_instagram_account",
                    "access_token": self.access_token,
                })
                url = f"{BASE_URL}/{page_id}?{data}"
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    res = json.loads(resp.read().decode())
                    ig = res.get("instagram_business_account") or res.get("connected_instagram_account")
                    if ig and isinstance(ig, dict) and ig.get("id"):
                        return str(ig["id"])
            except Exception:
                pass

        try:
            data = urllib.parse.urlencode({
                "fields": "id,instagram_business_account,connected_instagram_account",
                "access_token": self.access_token,
            })
            url = f"{BASE_URL}/me/accounts?{data}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                contas = json.loads(resp.read().decode()).get("data", [])
                for conta in contas:
                    ig = conta.get("instagram_business_account") or conta.get("connected_instagram_account")
                    if ig and isinstance(ig, dict) and ig.get("id"):
                        return str(ig["id"])
        except Exception:
            pass
        return None

    def _request(self, method: str, path: str, params: dict) -> dict:
        data = urllib.parse.urlencode(params)
        url = f"{BASE_URL}/{path}"
        if method == "GET":
            req = urllib.request.Request(f"{url}?{data}", method="GET")
        else:
            req = urllib.request.Request(url, data=data.encode(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            try:
                err = json.loads(body).get("error", {})
                code = err.get("code")
                subcode = err.get("error_subcode")
                msg = f"{err.get('type')} ({code}/{subcode}): {err.get('message')}"
                if code == 100 and (subcode == 33 or "Unsupported post request" in str(err.get("message", ""))):
                    current_id = getattr(self, "account_id", "desconhecido")
                    msg += (
                        f" -> Diagnóstico: O objeto com ID '{current_id}' não existe ou não está acessível pelo token. "
                        "Certifique-se de que a conta do Instagram é Profissional (Business/Creator) e está vinculada "
                        "à Página do Facebook no Meta Business Suite."
                    )
            except json.JSONDecodeError:
                msg = body
            raise RuntimeError(f"HTTP {e.code}: {msg}") from e

    def get_account_info(self) -> dict:
        return self._request("GET", self.account_id, {
            "fields": "id,username,name,biography,followers_count,media_count",
            "access_token": self.access_token,
        })

    def _wait_container(self, creation_id: str, timeout: int = 90) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            info = self._request("GET", creation_id, {
                "fields": "status_code,status",
                "access_token": self.access_token,
            })
            status = info.get("status_code")
            if status == "FINISHED":
                return True
            if status == "ERROR":
                detalhe = info.get("status") or "sem detalhe adicional"
                raise RuntimeError(f"Falha no processamento da mídia {creation_id}: {detalhe}")
            time.sleep(3)
        return False

    def _upload_video_temp_cdn(self, video_path: Path) -> str:
        """Hospeda temporariamente (TTL 1h) o arquivo MP4 em URL pública HTTPS direta para ingestão da Meta Graph API."""
        import uuid

        video_bytes = video_path.read_bytes()

        # Provedor 1: Litterbox (Catbox) com expiração automática de 1 hora
        try:
            boundary = uuid.uuid4().hex
            parts = [
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"reqtype\"\r\n\r\nfileupload\r\n".encode(),
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"time\"\r\n\r\n1h\r\n".encode(),
                (
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"fileToUpload\"; filename=\"{video_path.name}\"\r\n"
                    f"Content-Type: video/mp4\r\n\r\n"
                ).encode() + video_bytes + b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
            req = urllib.request.Request(
                "https://litterbox.catbox.moe/resources/internals/api.php",
                data=b"".join(parts),
                method="POST",
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "User-Agent": "AfiliadosHub/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                public_url = resp.read().decode("utf-8", "replace").strip()
                if public_url.startswith("https://"):
                    return public_url
        except Exception:
            pass

        # Provedor 2 (fallback): 0x0.st
        boundary = uuid.uuid4().hex
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"expires\"\r\n\r\n1\r\n".encode(),
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{video_path.name}\"\r\n"
                f"Content-Type: video/mp4\r\n\r\n"
            ).encode() + video_bytes + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        req = urllib.request.Request(
            "https://0x0.st",
            data=b"".join(parts),
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "AfiliadosHub/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            public_url = resp.read().decode("utf-8", "replace").strip()
            if public_url.startswith("https://"):
                return public_url
        raise RuntimeError(f"Resposta inválida ao hospedar vídeo temporário: {public_url}")

    def publish_photo(self, image_url: str, caption: str) -> dict:
        """Publica uma foto no feed do Instagram."""
        container = self._request("POST", f"{self.account_id}/media", {
            "image_url": image_url,
            "caption": caption,
            "access_token": self.access_token,
        })
        creation_id = container["id"]
        self._wait_container(creation_id)
        return self._request("POST", f"{self.account_id}/media_publish", {
            "creation_id": creation_id,
            "access_token": self.access_token,
        })

    def publish_story(self, image_url: str) -> dict:
        """Publica uma foto nos Stories do Instagram (imagem visual)."""
        container = self._request("POST", f"{self.account_id}/media", {
            "image_url": image_url,
            "media_type": "STORIES",
            "access_token": self.access_token,
        })
        creation_id = container["id"]
        self._wait_container(creation_id)
        return self._request("POST", f"{self.account_id}/media_publish", {
            "creation_id": creation_id,
            "access_token": self.access_token,
        })

    def publish_reel(self, video_path: str | Path, caption: str) -> dict:
        """Publica um vídeo local como Reel no Instagram via video_url público efêmero (com fallback resumable)."""
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Arquivo de vídeo não encontrado: {video_path}")

        container_id = None
        try:
            public_video_url = self._upload_video_temp_cdn(video_path)
            init_res = self._request("POST", f"{self.account_id}/media", {
                "media_type": "REELS",
                "video_url": public_video_url,
                "caption": caption,
                "share_to_feed": "true",
                "access_token": self.access_token,
            })
            container_id = init_res["id"]
        except Exception:
            # Fallback para Resumable Upload caso o CDN temporário esteja indisponível
            file_size = os.path.getsize(video_path)
            init_res = self._request("POST", f"{self.account_id}/media", {
                "upload_type": "resumable",
                "media_type": "REELS",
                "caption": caption,
                "access_token": self.access_token,
            })
            container_id = init_res["id"]
            upload_uri = init_res["uri"]
            video_bytes = video_path.read_bytes()
            headers = {
                "Authorization": f"OAuth {self.access_token}",
                "file_size": str(file_size),
                "offset": "0",
                "Content-Type": "application/octet-stream",
            }
            req_up = urllib.request.Request(upload_uri, data=video_bytes, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req_up, timeout=120) as resp:
                    json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                raise RuntimeError(f"Erro no upload do Reel: {e.read().decode('utf-8', 'replace')}") from e

        # Aguardar processamento do Reel na Meta
        if not self._wait_container(container_id, timeout=120):
            raise RuntimeError(f"Timeout aguardando processamento do container de Reel {container_id}")

        # Publicar Reel
        return self._request("POST", f"{self.account_id}/media_publish", {
            "creation_id": container_id,
            "access_token": self.access_token,
        })

    def publish_reel_from_image(self, image_path: str | Path, caption: str, duration: int = 5) -> dict:
        """Converte imagem 9:16 em vídeo MP4 compatível com Reels e publica no Instagram."""
        import shutil
        import subprocess

        image_path = Path(image_path).resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"Imagem não encontrada: {image_path}")

        video_mp4 = image_path.with_suffix(".mp4")

        # Se o MP4 já foi gerado anteriormente e está íntegro, reutiliza diretamente
        if video_mp4.exists() and video_mp4.stat().st_size >= 50000:
            return self.publish_reel(video_mp4, caption)

        ffmpeg_candidates = [
            shutil.which("ffmpeg"),
            "/usr/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "/opt/homebrew/bin/ffmpeg",
        ]
        ffmpeg_bin = next((c for c in ffmpeg_candidates if c and Path(c).exists()), None)
        if not ffmpeg_bin:
            raise FileNotFoundError(
                "Utilitário 'ffmpeg' não encontrado no sistema ou container. "
                "Para contêineres Docker, execute: docker compose up -d --build para instalar o ffmpeg."
            )

        cmd = [
            str(ffmpeg_bin),
            "-y",
            "-loop", "1",
            "-framerate", "30",
            "-i", str(image_path),
            "-f", "lavfi",
            "-i", f"anoisesrc=d={duration}:c=pink:r=48000:a=0.002,aformat=channel_layouts=stereo",
            "-t", str(duration),
            "-vf", "scale=1080:1920,format=yuv420p",
            "-c:v", "libx264",
            "-profile:v", "high",
            "-level", "4.1",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-g", "30",
            "-b:v", "1800k",
            "-maxrate", "2500k",
            "-bufsize", "5000k",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "48000",
            "-ac", "2",
            "-shortest",
            "-movflags", "+faststart",
            str(video_mp4),
        ]

        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self.publish_reel(video_mp4, caption)

if __name__ == "__main__":
    client = InstagramClient()
    print("== Conta do Instagram ==")
    print(json.dumps(client.get_account_info(), indent=2, ensure_ascii=False))
