"""Cliente da TikTok Content Posting API v2 para publicação direta de vídeos, apenas stdlib."""
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shopee.client import load_env

BASE_API_URL = "https://open.tiktokapis.com/v2"
AUTH_BASE_URL = "https://www.tiktok.com/v2/auth/authorize"


class TikTokClient:
    """Cliente oficial da API v2 do TikTok para postagem direta de vídeos."""

    def __init__(
        self,
        access_token: str | None = None,
        client_key: str | None = None,
        client_secret: str | None = None,
    ):
        load_env()
        self.client_key = client_key or os.environ.get("TIKTOK_KEY")
        self.client_secret = client_secret or os.environ.get("TIKTOK_SECRET")
        self.access_token = access_token or os.environ.get("TIKTOK_ACCESS_TOKEN")

        if not self.client_key or not self.client_secret:
            raise RuntimeError("Credenciais TIKTOK_KEY e/ou TIKTOK_SECRET ausentes no .env")

    def obter_url_autorizacao(
        self,
        redirect_uri: str,
        state: str = "afiliados_tiktok",
        scopes: list[str] | None = None,
    ) -> str:
        """Gera a URL OAuth 2.0 para o criador autorizar o aplicativo com permissões de publicação."""
        if not scopes:
            scopes = ["user.info.basic", "video.publish", "video.upload"]

        params = {
            "client_key": self.client_key,
            "scope": ",".join(scopes),
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"{AUTH_BASE_URL}/?{urllib.parse.urlencode(params)}"

    def trocar_code_por_token(self, code: str, redirect_uri: str) -> dict:
        """Troca o authorization_code concedido pelo usuário pelo access_token e refresh_token."""
        url = f"{BASE_API_URL}/oauth/token/"
        data = urllib.parse.urlencode({
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode())
                if "access_token" in res:
                    self.access_token = res["access_token"]
                return res
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise RuntimeError(f"HTTP {e.code} ao trocar code por token TikTok: {body}") from e

    def renovar_token(self, refresh_token: str) -> dict:
        """Renova o access_token utilizando o refresh_token."""
        url = f"{BASE_API_URL}/oauth/token/"
        data = urllib.parse.urlencode({
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode())
                if "access_token" in res:
                    self.access_token = res["access_token"]
                return res
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise RuntimeError(f"HTTP {e.code} ao renovar token TikTok: {body}") from e

    def _post_json(self, path: str, payload: dict) -> dict:
        if not self.access_token:
            raise RuntimeError(
                "TIKTOK_ACCESS_TOKEN ausente. É necessário autorizar o aplicativo via OAuth 2.0 para obter o token de usuário."
            )

        url = f"{BASE_API_URL}/{path}"
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                res = json.loads(resp.read().decode())
                err = res.get("error", {})
                if err.get("code") and err.get("code") != "ok":
                    raise RuntimeError(f"TikTok API Error ({err.get('code')}): {err.get('message')}")
                return res
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise RuntimeError(f"HTTP {e.code} na chamada TikTok /{path}: {body}") from e

    def consultar_status_publicacao(self, publish_id: str) -> dict:
        """Consulta o status de processamento da publicação no TikTok."""
        return self._post_json("post/publish/status/fetch/", {"publish_id": publish_id})

    def aguardar_publicacao(self, publish_id: str, timeout: int = 120, intervalo: int = 5) -> dict:
        """Realiza polling até que o vídeo seja publicado com sucesso ou falhe."""
        inicio = time.time()
        while time.time() - inicio < timeout:
            res = self.consultar_status_publicacao(publish_id)
            data = res.get("data", {})
            status = data.get("status")
            if status == "SUCCESS":
                return data
            if status == "FAILED":
                motivo = data.get("fail_reason", "Desconhecido")
                raise RuntimeError(f"Falha na publicação do vídeo no TikTok (publish_id: {publish_id}): {motivo}")
            time.sleep(intervalo)
        raise TimeoutError(f"Tempo limite excedido aguardando processamento do TikTok (publish_id: {publish_id})")

    def publicar_video(
        self,
        video_path: str | Path,
        title: str,
        privacy_level: str = "PUBLIC_TO_EVERYONE",
        disable_duet: bool = False,
        disable_comment: bool = False,
        disable_stitch: bool = False,
        video_cover_timestamp_ms: int = 1000,
        aguardar_conclusao: bool = True,
    ) -> dict:
        """
        Publica um arquivo de vídeo local no TikTok utilizando o fluxo oficial de 3 etapas da Content Posting API:
        1. Inicialização (init) com FILE_UPLOAD
        2. Upload binário em partes (PUT)
        3. Polling de status até confirmação de publicação
        """
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo de vídeo não encontrado: {path}")

        video_bytes = path.read_bytes()
        video_size = len(video_bytes)
        if video_size == 0:
            raise ValueError(f"O arquivo de vídeo está vazio: {path}")

        # Definindo tamanho de chunk: mínimo 5MB para vídeos grandes, ou o tamanho total se < 5MB
        chunk_size = video_size if video_size <= 5 * 1024 * 1024 else 10 * 1024 * 1024
        total_chunks = math.floor(video_size / chunk_size)
        if total_chunks < 1:
            total_chunks = 1

        # Etapa 1: Inicializar publicação
        init_payload = {
            "post_info": {
                "title": title[:150],  # Limite máximo seguro de caracteres
                "privacy_level": privacy_level,
                "disable_duet": disable_duet,
                "disable_comment": disable_comment,
                "disable_stitch": disable_stitch,
                "video_cover_timestamp_ms": video_cover_timestamp_ms,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            },
        }

        init_res = self._post_json("post/publish/video/init/", init_payload)
        data = init_res.get("data", {})
        publish_id = data.get("publish_id")
        upload_url = data.get("upload_url")

        if not upload_url or not publish_id:
            raise RuntimeError(f"Resposta inválida da inicialização de vídeo TikTok: {init_res}")

        # Etapa 2: Upload binário para upload_url
        start_byte = 0
        for i in range(total_chunks):
            is_last = (i == total_chunks - 1)
            end_byte = video_size - 1 if is_last else (start_byte + chunk_size - 1)
            chunk_data = video_bytes[start_byte : end_byte + 1]

            headers = {
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes {start_byte}-{end_byte}/{video_size}",
                "Content-Length": str(len(chunk_data)),
            }
            req = urllib.request.Request(upload_url, data=chunk_data, headers=headers, method="PUT")
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    resp.read()
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                raise RuntimeError(
                    f"Erro no upload da parte {i+1}/{total_chunks} do vídeo TikTok: HTTP {e.code}: {body}"
                ) from e

            start_byte = end_byte + 1

        # Etapa 3: Aguardar processamento da publicação (opcional)
        if aguardar_conclusao:
            status_data = self.aguardar_publicacao(publish_id)
            return {
                "publish_id": publish_id,
                "status": "SUCCESS",
                "detalhes": status_data,
            }

        return {
            "publish_id": publish_id,
            "status": "PROCESSING",
        }
