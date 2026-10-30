"""Cliente mínimo da Meta Graph API para Páginas do Facebook, apenas stdlib."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shopee.client import load_env  # noqa: E402

GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v23.0")
BASE_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


class FacebookRateLimitError(RuntimeError):
    """Exceção disparada quando a Meta Graph API impõe bloqueio temporário de frequência no Facebook."""


_CODIGOS_RATE_LIMIT_META = {4, 17, 32, 368, 613}


class FacebookPageClient:
    def __init__(self):
        load_env()
        self.app_id = os.environ.get("META_APP_ID")
        self.app_secret = os.environ.get("META_APP_SECRET")
        self.page_id = os.environ.get("META_PAGE_ID")
        self.raw_token = os.environ.get("META_PAGE_TOKEN")
        self.page_token = self.raw_token
        missing = [k for k, v in {
            "META_APP_ID": self.app_id,
            "META_APP_SECRET": self.app_secret,
            "META_PAGE_ID": self.page_id,
            "META_PAGE_TOKEN": self.raw_token,
        }.items() if not v]
        if missing:
            raise RuntimeError(f"Variáveis ausentes no .env: {', '.join(missing)}")
        self._resolver_page_token_e_id()

    def _resolver_page_token_e_id(self) -> None:
        """Deriva o Page Access Token a partir de um System User / User Token e reconcilia o ID oficial da Página."""
        try:
            res = self._request("GET", self.page_id, {
                "fields": "id,access_token",
                "access_token": self.raw_token,
            })
            if res.get("id"):
                self.page_id = str(res["id"])
            if res.get("access_token"):
                self.page_token = res["access_token"]
                return
        except Exception:
            pass

        try:
            contas = self._request("GET", "me/accounts", {
                "fields": "id,name,access_token",
                "access_token": self.raw_token,
            }).get("data", [])
            if contas:
                escolhida = next((c for c in contas if str(c.get("id")) == str(self.page_id)), contas[0])
                if escolhida.get("id"):
                    self.page_id = str(escolhida["id"])
                if escolhida.get("access_token"):
                    self.page_token = escolhida["access_token"]
        except Exception:
            pass

    def _request(self, method: str, path: str, params: dict) -> dict:
        data = urllib.parse.urlencode(params)
        url = f"{BASE_URL}/{path}"
        if method == "GET":
            req = urllib.request.Request(f"{url}?{data}", method="GET")
        else:
            req = urllib.request.Request(url, data=data.encode(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            code = None
            try:
                err = json.loads(body).get("error", {})
                code = err.get("code")
                msg = f"{err.get('type')} ({code}/{err.get('error_subcode')}): {err.get('message')}"
            except json.JSONDecodeError:
                msg = body
            if code in _CODIGOS_RATE_LIMIT_META:
                raise FacebookRateLimitError(
                    f"Meta Graph API Rate Limit / Cooldown ativo no Facebook (HTTP {e.code}): {msg}"
                ) from e
            raise RuntimeError(f"HTTP {e.code}: {msg}") from e

    def debug_token(self) -> dict:
        """Valida o token configurado sem expor o valor."""
        res = self._request("GET", "debug_token", {
            "input_token": self.raw_token,
            "access_token": f"{self.app_id}|{self.app_secret}",
        })["data"]
        return {
            "is_valid": res.get("is_valid"),
            "type": res.get("type"),
            "app_id": res.get("app_id"),
            "profile_id": res.get("profile_id"),
            "expires_at": res.get("expires_at"),
            "scopes": res.get("scopes"),
        }

    def page_info(self) -> dict:
        return self._request("GET", self.page_id, {
            "fields": "id,name,link,followers_count",
            "access_token": self.page_token,
        })

    def publish_post(self, message: str, link: str | None = None) -> dict:
        params = {"message": message, "access_token": self.page_token}
        if link:
            params["link"] = link
        return self._request("POST", f"{self.page_id}/feed", params)

    def publish_photo(self, image_url: str, caption: str) -> dict:
        return self._request("POST", f"{self.page_id}/photos", {
            "url": image_url,
            "caption": caption,
            "access_token": self.page_token,
        })

    def publish_photo_file(self, file_path: str | Path, caption: str) -> dict:
        """Publica imagem local enviando o arquivo como multipart/form-data."""
        import mimetypes
        import uuid

        path = Path(file_path)
        boundary = uuid.uuid4().hex
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        parts = []
        for name, value in {"caption": caption, "access_token": self.page_token}.items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
            )
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"source\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n".encode() + path.read_bytes() + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            f"{BASE_URL}/{self.page_id}/photos",
            data=b"".join(parts),
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}") from e

    def upload_photo_to_cdn(self, file_path: str | Path) -> str:
        """Faz upload de arquivo local sem publicar no feed e retorna sua URL pública na CDN da Meta."""
        import mimetypes
        import uuid

        path = Path(file_path)
        boundary = uuid.uuid4().hex
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        parts = []
        for name, value in {"published": "false", "access_token": self.page_token}.items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
            )
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"source\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n".encode() + path.read_bytes() + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            f"{BASE_URL}/{self.page_id}/photos",
            data=b"".join(parts),
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                photo_id = json.loads(resp.read().decode())["id"]
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}") from e

        # Consulta a URL pública na CDN
        info = self._request("GET", photo_id, {
            "fields": "images",
            "access_token": self.page_token,
        })
        return info["images"][0]["source"]

    def publish_reel(self, video_path: str | Path, description: str) -> dict:
        """Publica um vídeo vertical (9:16) na Página do Facebook via Graph Video API (multipart/form-data)."""
        import mimetypes
        import uuid

        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Arquivo de vídeo não encontrado: {video_path}")

        boundary = uuid.uuid4().hex
        mime = mimetypes.guess_type(video_path.name)[0] or "video/mp4"
        parts = []
        for name, value in {
            "description": description,
            "access_token": self.page_token,
        }.items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
            )
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"source\"; filename=\"{video_path.name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n".encode() + video_path.read_bytes() + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())

        video_url = f"https://graph-video.facebook.com/{GRAPH_VERSION}/{self.page_id}/videos"
        req = urllib.request.Request(
            video_url,
            data=b"".join(parts),
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                res = json.loads(resp.read().decode())
                video_id = str(res.get("id") or res.get("video_id") or "")
                return {
                    "video_id": video_id,
                    "id": video_id,
                    "post_id": video_id,
                    "success": bool(video_id),
                    "details": res,
                }
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise RuntimeError(f"Erro no envio do vídeo/Reel para o Facebook (HTTP {e.code}): {body}") from e

    def get_reel_status(self, video_id: str) -> dict:
        """Consulta o status de processamento de um Reel na Meta."""
        return self._request("GET", video_id, {
            "fields": "status,published",
            "access_token": self.page_token,
        })

    def publish_reel_from_image(self, image_path: str | Path, description: str, duration: int = 5) -> dict:
        """Converte imagem vertical 9:16 em vídeo MP4 compatível com Reels e publica na Página do Facebook."""
        import shutil
        import subprocess

        image_path = Path(image_path).resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"Imagem não encontrada: {image_path}")

        video_mp4 = image_path.with_suffix(".mp4")

        # Se o MP4 já foi gerado anteriormente e está íntegro, reutiliza diretamente
        if video_mp4.exists() and video_mp4.stat().st_size >= 50000:
            return self.publish_reel(video_mp4, description)

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
        return self.publish_reel(video_mp4, description)


if __name__ == "__main__":
    client = FacebookPageClient()
    print("== Token ==")
    print(json.dumps(client.debug_token(), indent=2, ensure_ascii=False))
    print("== Página ==")
    print(json.dumps(client.page_info(), indent=2, ensure_ascii=False))
