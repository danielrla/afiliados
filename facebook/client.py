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


class FacebookPageClient:
    def __init__(self):
        load_env()
        self.app_id = os.environ.get("META_APP_ID")
        self.app_secret = os.environ.get("META_APP_SECRET")
        self.page_id = os.environ.get("META_PAGE_ID")
        self.page_token = os.environ.get("META_PAGE_TOKEN")
        missing = [k for k, v in {
            "META_APP_ID": self.app_id,
            "META_APP_SECRET": self.app_secret,
            "META_PAGE_ID": self.page_id,
            "META_PAGE_TOKEN": self.page_token,
        }.items() if not v]
        if missing:
            raise RuntimeError(f"Variáveis ausentes no .env: {', '.join(missing)}")

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
            try:
                err = json.loads(body).get("error", {})
                msg = f"{err.get('type')} ({err.get('code')}/{err.get('error_subcode')}): {err.get('message')}"
            except json.JSONDecodeError:
                msg = body
            raise RuntimeError(f"HTTP {e.code}: {msg}") from e

    def debug_token(self) -> dict:
        """Valida o token da Página sem expor o valor."""
        res = self._request("GET", "debug_token", {
            "input_token": self.page_token,
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



if __name__ == "__main__":
    client = FacebookPageClient()
    print("== Token ==")
    print(json.dumps(client.debug_token(), indent=2, ensure_ascii=False))
    print("== Página ==")
    print(json.dumps(client.page_info(), indent=2, ensure_ascii=False))
