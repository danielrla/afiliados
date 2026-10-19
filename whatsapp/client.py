"""Cliente Z-API para envio de mensagens e imagens no WhatsApp, apenas stdlib."""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shopee.client import load_env  # noqa: E402


class ZApiClient:
    def __init__(self):
        load_env()
        self.instance_id = os.environ.get("ZAPI_ID")
        self.instance_token = os.environ.get("ZAPI_TOKEN")
        self.client_token = os.environ.get("ZAPI_CLIENT_TOKEN")
        if not self.instance_id or not self.instance_token:
            raise RuntimeError("ZAPI_ID ou ZAPI_TOKEN ausentes no .env")
        self.base_url = f"https://api.z-api.io/instances/{self.instance_id}/token/{self.instance_token}"

    def _request(self, method: str, endpoint: str, body: dict | None = None) -> dict:
        url = f"{self.base_url}/{endpoint}"
        headers = {"Content-Type": "application/json"}
        if self.client_token:
            headers["Client-Token"] = self.client_token
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")
            raise RuntimeError(f"HTTP {e.code}: {msg}") from e

    def get_status(self) -> dict:
        return self._request("GET", "status")

    def get_chats(self) -> list:
        return self._request("GET", "chats")

    def find_group_by_name(self, group_name: str) -> dict | None:
        chats = self.get_chats()
        target = group_name.strip().lower()
        for chat in chats:
            name = (chat.get("name") or chat.get("subject") or "").strip().lower()
            if target in name:
                return chat
        return None

    def _prepare_image_payload(self, image: str | Path) -> str:
        """Prepara o payload de imagem para a Z-API, convertendo arquivos locais para Base64 Data URI."""
        import base64
        caminho_local = None
        if isinstance(image, Path):
            caminho_local = image
        elif isinstance(image, str) and not (image.startswith("http://") or image.startswith("https://") or image.startswith("data:")):
            p = Path(image)
            if p.exists():
                caminho_local = p

        if caminho_local and caminho_local.exists():
            ext = caminho_local.suffix.lower()
            mime = "image/png" if ext == ".png" else ("image/webp" if ext == ".webp" else "image/jpeg")
            b64_data = base64.b64encode(caminho_local.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{b64_data}"

        return str(image)

    def send_text(self, phone: str, message: str) -> dict:
        return self._request("POST", "send-text", {
            "phone": phone,
            "message": message,
        })

    def send_image(self, phone: str, image_url: str | Path, caption: str) -> dict:
        image_payload = self._prepare_image_payload(image_url)
        return self._request("POST", "send-image", {
            "phone": phone,
            "image": image_payload,
            "caption": caption,
        })

    def send_to_group(self, caption: str, image_url: str | Path | None = None, group_id: str | None = None) -> dict:
        gid = group_id or os.environ.get("ZAPI_GROUP_ID")
        if not gid:
            grp = self.find_group_by_name("Dicas Shopee")
            if not grp:
                raise RuntimeError("Grupo Dicas Shopee não encontrado")
            gid = grp["phone"]
        if image_url:
            return self.send_image(gid, image_url, caption)
        return self.send_text(gid, caption)


if __name__ == "__main__":
    client = ZApiClient()
    print("== Status Z-API ==")
    print(json.dumps(client.get_status(), indent=2, ensure_ascii=False))
    print("== Buscando Grupo ==")
    group = client.find_group_by_name("Dicas Shopee")
    print(json.dumps(group, indent=2, ensure_ascii=False))
