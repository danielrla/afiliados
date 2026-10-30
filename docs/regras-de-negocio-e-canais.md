# Regras de Negócio e Matriz de Publicação por Canal

Este documento estabelece as regras funcionais obrigatórias para geração de mídia, uso de templates e disparo nos canais sociais do projeto **Afiliados Multi-Channel Hub**.

---

## 1. Matriz Oficial dos 6 Canais Obrigatórios (`CANAIS_OBRIGATORIOS`)

Todo produto cadastrado deve cumprir o ciclo de publicação nos 6 canais abaixo. A regra de mídia diferencia explicitamente o **WhatsApp** e o **Post no Feed do Facebook** (que usam a imagem pura do link do produto, sem template) dos demais canais visuais que aplicam as templates de `instagran/templates/`:

| Ordem | Canal (`canais_status.canal`) | Destino | Regra Obrigatória de Mídia | Template em `instagran/templates/` | Método de Envio |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **1/6** | `whatsapp` | Grupo WhatsApp (`Linkolandiabr`) | **Imagem original extraída do link do produto (`primary_image`), SEM aplicar template** | **Nenhuma (usa `primary_image` direto do link)** | `ZApiClient.send_to_group(caption_wa, image_url=primary_image)` |
| **2/6** | `facebook` | Feed da Página Facebook (`Linkolandiabr`) | **Imagem original extraída do link do produto (`primary_image`), SEM aplicar template** | **Nenhuma (usa `primary_image` direto do link)** | `FacebookPageClient.publish_photo(primary_image, caption_fb)` |
| **3/6** | `facebook_reels` | Reels / Vídeos da Página Facebook (`Linkolandiabr`) | Vídeo vertical `1080x1920` (`.mp4`, `30 fps`, H.264 + áudio AAC `128 kbps`) gerado da arte vertical | `template_reels.html` -> `{id}_reeals.mp4` | `FacebookPageClient.publish_reel()` via `graph-video.facebook.com/v23.0/{page_id}/videos` |
| **4/6** | `instagram_stories` | Stories do Instagram (`@linkolandiabr`) | Arte vertical `1080x1920` com identidade Linkolândia | `template_stories.html` -> `{id}_stories.png` | `InstagramClient.publish_story()` (`media_type=STORIES`) |
| **5/6** | `instagram_post` | Feed do Instagram (`@linkolandiabr`) | Arte quadrada `1080x1080` com identidade Linkolândia | `template_post.html` -> `{id}_post.png` | `InstagramClient.publish_photo()` |
| **6/6** | `instagram_reels` | Reels do Instagram (`@linkolandiabr`) | Vídeo vertical `1080x1920` (`.mp4`, `30 fps`, H.264 + áudio AAC `128 kbps`) gerado da arte vertical | `template_reels.html` -> `{id}_reeals.mp4` | `InstagramClient.publish_reel()` (`media_type=REELS` via `video_url`) |

---

## 2. Identidade Visual e Templates (`instagran/templates/`)

Os arquivos localizados em `instagran/templates/` definem o padrão visual da marca **Linkolândia**:

- **Ícone Oficial:** `instagran/templates/linkolandia.png` (embutido automaticamente como Data URI Base64 durante a renderização em `instagran/tratarParaInstagran.py`).
- **Paleta de Cores Oficial:**
  - Azul Marinho Principal (Navy): `#132B4A` / `#0B1B32`
  - Dourado / Amarelo (Gold): `#F4B84B` / `#D99014`
- **Arquivos de Template:**
  - `instagran/templates/template_post.html` (`1080x1080`, formato 1:1 para Feed do Instagram e WhatsApp).
  - `instagran/templates/template_stories.html` (`1080x1920`, formato 9:16 para Stories do Instagram).
  - `instagran/templates/template_reels.html` e `instagran/templates/template_reeals.html` (`1080x1920`, formato 9:16 para conversão em vídeo `.mp4` de Reels).

---

## 3. Regra de Cache e Invalidação Automática (`localizar_artes_produto`)

As artes renderizadas para cada produto são armazenadas em `db/img/<YYYY-MM-DD>/<item_id>/`:
- `original.jpg`: fotografia original baixada da CDN da Shopee.
- `<item_id>_post.png`: arte renderizada de `template_post.html`.
- `<item_id>_stories.png`: arte renderizada de `template_stories.html`.
- `<item_id>_reeals.png` / `<item_id>_reels.png`: arte vertical renderizada de `template_reels.html`.
- `<item_id>_reeals.mp4` / `<item_id>_reels.mp4`: vídeo codificado com H.264 High Profile (`30 fps`) e trilha de áudio estéreo AAC-LC (`48 kHz`, `128 kbps`).

**Invalidação por Timestamp (`st_mtime`):**
- `localizar_artes_produto()` em `db/controle.py` verifica a data de modificação (`st_mtime`) de todos os arquivos em `instagran/templates/` (`.html` e `.png`).
- Se qualquer arquivo em cache tiver `st_mtime` anterior à última alteração de `instagran/templates/`, ou se o arquivo `.mp4` tiver menos de `50 KB`, o cache é descartado e `gerar_todas_imagens()` renderiza novas artes atualizadas.

---

## 4. Rastreamento de Links e Reenvio Cirúrgico

1. **Links Rastreados por Canal (`ShopeeAffiliateClient.gerar_link_canal`):**
   - Cada canal gera seu próprio shortlink na Shopee Open API com `sub_ids` específicos (`whatsapp`, `facebook`, `facebook_reels`, `instagram_stories`, `instagram_post`, `instagram_reels`), permitindo atribuir vendas e comissões exatamente ao canal de origem.
2. **Idempotência de Ingestão e Disparo:**
   - Produtos com `item_id` já registrado em `produtos_publicados` não são sobrescritos na importação de planilhas CSV.
   - Nos reenvios (`reenviar_falhas.py` ou botão de reenvio no painel), apenas os canais cujo status em `canais_status` seja diferente de `SUCESSO` são executados.
