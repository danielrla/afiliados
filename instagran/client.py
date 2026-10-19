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
        self.account_id = account_id or os.environ.get("INSTAGRAM_ACCOUNT_ID") or "17841451954697561"
        # O token pode estar em META_PAGE_TOKEN ou META_USER_TOKEN
        self.access_token = access_token or os.environ.get("META_PAGE_TOKEN") or os.environ.get("META_USER_TOKEN")
        if not self.access_token:
            raise RuntimeError("Token da Meta ausente no .env")

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
                msg = f"{err.get('type')} ({err.get('code')}/{err.get('error_subcode')}): {err.get('message')}"
            except json.JSONDecodeError:
                msg = body
            raise RuntimeError(f"HTTP {e.code}: {msg}") from e

    def get_account_info(self) -> dict:
        return self._request("GET", self.account_id, {
            "fields": "id,username,name,biography,followers_count,media_count",
            "access_token": self.access_token,
        })

    def _wait_container(self, creation_id: str, timeout: int = 45) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            status = self._request("GET", creation_id, {
                "fields": "status_code",
                "access_token": self.access_token,
            }).get("status_code")
            if status == "FINISHED":
                return True
            if status == "ERROR":
                raise RuntimeError(f"Falha no processamento da mídia {creation_id}")
            time.sleep(2)
        return False

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
        """Publica um vídeo local como Reel no Instagram usando a API oficial Resumable Upload."""
        import subprocess

        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Arquivo de vídeo não encontrado: {video_path}")

        file_size = os.path.getsize(video_path)

        # 1. Iniciar sessão resumable
        init_res = self._request("POST", f"{self.account_id}/media", {
            "upload_type": "resumable",
            "media_type": "REELS",
            "caption": caption,
            "access_token": self.access_token,
        })
        container_id = init_res["id"]
        upload_uri = init_res["uri"]

        # 2. Upload binário para rupload.facebook.com
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

        # 3. Aguardar processamento do Reel na Meta
        self._wait_container(container_id, timeout=90)

        # 4. Publicar Reel
        return self._request("POST", f"{self.account_id}/media_publish", {
            "creation_id": container_id,
            "access_token": self.access_token,
        })

    def publish_reel_from_image(self, image_path: str | Path, caption: str, duration: int = 5) -> dict:
        """Converte imagem 9:16 em vídeo MP4 compatível com Reels e publica no Instagram."""
        import subprocess

        image_path = Path(image_path).resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"Imagem não encontrada: {image_path}")

        video_mp4 = image_path.with_suffix(".mp4")
        ffmpeg_bin = "/opt/homebrew/bin/ffmpeg" if Path("/opt/homebrew/bin/ffmpeg").exists() else "ffmpeg"

        cmd = [
            ffmpeg_bin,
            "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-c:v", "libx264",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-c:a", "aac",
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
