# Afiliados Multi-Channel Hub

Plataforma integrada para automação de publicações de afiliados Shopee em múltiplos canais digitais (WhatsApp, Facebook e Instagram), contando com esteira de geração automatizada de artes gráficas, persistência transacional em SQLite e painel de controle administrativo em Angular 22.

---

## 🚀 Visão Geral da Arquitetura

O sistema automatiza o ciclo completo de divulgação de produtos de afiliados:
1. **Ingestão e Carga:** Leitura de planilhas de ofertas CSV com validação de esquema e proteção estrita contra registros duplicados baseada no `Item ID`.
2. **Renderização de Artes:** Geração dinâmica de artes visuais personalizadas para Instagram Stories (9:16), Feed (1:1) e Reels com renderização de HTML em alta resolução.
3. **Distribuição Multi-Canal:** Disparo sequencial e rastreável nos 5 canais obrigatórios:
   * **WhatsApp:** Mensagens formatadas com link e mídia via Z-API.
   * **Facebook:** Publicações na página oficial via Graph API.
   * **Instagram Stories:** Envio de imagem formatada para stories.
   * **Instagram Feed:** Postagens no feed com legenda otimizada.
   * **Instagram Reels:** Publicações de vídeo/reels automatizadas.
4. **Auditoria e Reenvio Cirúrgico:** Registro de logs por canal no SQLite, permitindo reprocessar exclusivamente os canais que falharam sem reenviar os já concluídos com sucesso.
5. **Interface de Gestão:** Aplicação Web SPA moderna desenvolvida em Angular 22 com paginação no servidor, seleção múltipla de produtos, disparo em lote e exclusão seletiva.

---

## 🛠️ Stack Tecnológica

* **Backend:** Python 3.14, FastAPI, Uvicorn, Requests, Playwright.
* **Banco de Dados:** SQLite3 (`db/publicacoes.db`), gerenciado nativamente por `db/controle.py`.
* **Frontend:** Angular 22, TypeScript 6.0, HTML5 Semântico, CSS Vanilla Modular (Design System com paleta suave e moderna).
* **Contêineres e Orquestração:** Docker, Docker Compose, Alpine Linux, rede `containers`, fuso horário `America/Cuiaba`.

---

## 📁 Estrutura do Repositório

```text
├── .agents/                    # Diretrizes operacionais e de governança para IA
├── db/                         # Camada de persistência SQLite
│   ├── controle.py             # Módulo de CRUD, métricas, auditoria e controle de duplicidade
│   └── publicacoes.db          # Arquivo do banco de dados relacional local
├── facebook/                   # Integração com a Graph API do Facebook Pages
│   └── client.py               # Cliente HTTP de publicação de imagens e links
├── frontend/                   # Interface administrativa em Angular 22
│   ├── src/app/                # Componentes, modelos e serviços reativos (Signals)
│   ├── index_preview.html      # Interface prévia unificada servida pelo FastAPI
│   └── Dockerfile              # Imagem Node 22 com fuso horário Cuiabá
├── instagran/                  # Motor de artes gráficas e Instagram Graph API
│   ├── templates/              # Templates HTML/CSS para Stories, Feed e Reels
│   ├── tratarParaInstagran.py  # Renderizador Playwright para conversão em imagem
│   └── client.py               # Cliente de publicação do Instagram
├── produtos/                   # Catálogos CSV e utilitários de scraping Shopee
│   └── reader.py               # Leitor e extrator de imagens de produtos
├── shopee/                     # Módulo de integração com a Open API da Shopee
│   └── client.py               # Cliente GraphQL para geração de links e metadados
├── whatsapp/                   # Integração com WhatsApp via Z-API
│   └── client.py               # Cliente de mensagens de texto e mídia
├── docker-compose.yml          # Definição dos serviços backend e frontend
├── Dockerfile                  # Imagem Python 3.14 para a API FastAPI
├── publicar.py                 # Script de publicação em lote via terminal
├── reenviar_falhas.py          # Utilitário de reprocessamento cirúrgico de pendências
├── server.py                   # API REST FastAPI e servidor estático
└── subir_containers.sh         # Script utilitário para subida dos contêineres
```

---

## ⚙️ Variáveis de Ambiente

Crie um arquivo `.env` na raiz do repositório baseado nos parâmetros a seguir:

```ini
# --- Meta Graph API (Facebook e Instagram) ---
META_APP_ID=seu_app_id
META_APP_SECRET=seu_app_secret
META_PAGE_ID=sua_page_id
META_PAGE_TOKEN=seu_page_access_token
INSTAGRAM_ACCOUNT_ID=seu_instagram_account_id

# --- WhatsApp (Z-API) ---
ZAPI_ID=sua_instancia_zapi
ZAPI_TOKEN=seu_token_zapi
ZAPI_CLIENT_TOKEN=seu_client_token_zapi
ZAPI_GROUP_ID=id_do_grupo_whatsapp
ZAPI_DELAY_MESSAGE=10

# --- Shopee Affiliate Open API ---
SHOPEE_AFFILIATE_APP_ID=seu_shopee_app_id
SHOPEE_AFFILIATE_SECRET=seu_shopee_secret

# --- Configurações Gerais da Aplicação ---
DELAY_ENTRE_PRODUTOS=60
TIMEZONE=America/Cuiaba
```

---

## 🐳 Executando com Docker Compose

O projeto está configurado para execução conteinerizada padronizada na rede externa `containers` e timezone `America/Cuiaba`:

```bash
# 1. Criação da rede Docker (caso ainda não exista)
docker network create containers

# 2. Inicialização dos contêineres com build
docker compose up -d --build

# 3. Verificação do status dos serviços
docker compose ps
```

### URLs de Acesso Local
* **Painel Web Angular:** `http://localhost:4200`
* **API REST Backend:** `http://localhost:8000`
* **Documentação Swagger Interativa:** `http://localhost:8000/docs`
* **Preview Alternativo Integrado:** `http://localhost:8000/`

---

## 💻 Execução Local (Sem Docker)

### Backend (Python)

```bash
# Instalação de dependências
pip install -r requirements.txt

# Inicialização da API FastAPI com recarregamento contínuo
python server.py
```

### Frontend (Angular)

```bash
cd frontend
npm install --legacy-peer-deps
npm start
```

---

## 📋 Comandos e Scripts de Linha de Comando

* **Publicar catálogo de produtos com intervalo:**
  ```bash
  python publicar.py produtos/001.csv --delay 45
  ```
* **Simular publicação sem efetuar envios reais (Dry-Run):**
  ```bash
  python publicar.py produtos/001.csv --dry-run
  ```
* **Exibir relatório consolidado de entregas no terminal:**
  ```bash
  python publicar.py --status
  ```
* **Reprocessar cirurgicamente apenas os canais com falha/pendência:**
  ```bash
  python reenviar_falhas.py
  ```

---

## 🛡️ Regras de Integridade e Negócio

* **Confinamento de Escopo:** Todas as alterações de código e manipulações de arquivos ocorrem estritamente na pasta raiz do projeto.
* **Idempotência de Ingestão:** Ao importar produtos via planilha CSV ou interface gráfica, registros com `Item ID` já existente no banco de dados são automaticamente ignorados para evitar duplicidade e manter o histórico de auditoria intacto.
* **Segurança de Dados:** O arquivo `.gitignore` previne a indexação acidental de credenciais (`.env`), anotações privadas, dumps de banco SQLite locais e arquivos de compilação.
