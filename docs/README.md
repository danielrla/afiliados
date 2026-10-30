# Documentação Oficial: Afiliados Multi-Channel Hub (Linkolândia)

Bem-vindo à documentação técnica e de regras de negócio do projeto **Afiliados Multi-Channel Hub**. Esta pasta (`docs/`) concentra a referência canônica sobre arquitetura, fluxos de dados, regras de publicação por canal e operação do sistema.

---

## Índice da Documentação

1. **[Arquitetura e Fluxos (`docs/arquitetura-e-fluxos.md`)](arquitetura-e-fluxos.md)**
   - Visão em camadas (Backend FastAPI, Frontend Angular 22, Motor de Artes Chromium/FFmpeg e SQLite).
   - Diagrama do pipeline de ingestão, renderização e publicação nos 6 canais.
   - Modelo de dados relacional do banco `db/publicacoes.db`.
2. **[Regras de Negócio e Canais (`docs/regras-de-negocio-e-canais.md`)](regras-de-negocio-e-canais.md)**
   - Matriz oficial de mídia por canal (incluindo a regra obrigatória de que **WhatsApp** e **Post no Feed do Facebook** usam a imagem original do link sem aplicar template, enquanto **Facebook Reels**, **Instagram Stories**, **Instagram Post** e **Instagram Reels** aplicam as templates de `instagran/templates/`).
   - Identidade visual Linkolândia (`linkolandia.png`, azul `#132B4A`, dourado `#F4B84B`) e invalidação automática de cache por timestamp (`st_mtime`).
   - Idempotência por `Item ID`, rastreamento de links por `sub_id` na Shopee Open API e reenvio cirúrgico de falhas.
3. **[API REST, CLI e Operação de Containers (`docs/api-e-operacao.md`)](api-e-operacao.md)**
   - Referência das rotas FastAPI (`server.py`).
   - Guia dos utilitários de linha de comando (`publicar.py`, `reenviar_falhas.py`, `subir_containers.sh`, `publicar_docker.sh`).
   - Padrões de infraestrutura Docker (rede `containers`, timezone `America/Cuiaba`, imagens multi-arquitetura `allinefreire/afiliados`).

---

## Resumo Rápido da Stack

| Camada | Tecnologia | Diretório / Arquivo Principal |
| :--- | :--- | :--- |
| **API & Orquestração** | Python 3.14, FastAPI, Uvicorn | `server.py`, `publicar.py`, `reenviar_falhas.py` |
| **Persistência & Auditoria** | SQLite3 | `db/controle.py`, `db/publicacoes.db` |
| **Motor de Templates e Vídeo** | HTML5/CSS3, Chromium Headless, FFmpeg | `instagran/tratarParaInstagran.py`, `instagran/templates/` |
| **Integrações Sociais** | Meta Graph API `v23.0`, Z-API, Shopee GraphQL | `facebook/client.py`, `instagran/client.py`, `whatsapp/client.py`, `shopee/client.py` |
| **Painel Administrativo** | Angular 22, TypeScript, CSS Vanilla Modular | `frontend/` |
| **Containers** | Docker Compose, Buildx (`amd64`/`arm64`) | `docker-compose.yml`, `Dockerfile`, `frontend/Dockerfile`, `publicar_docker.sh` |
