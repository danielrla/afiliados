# API REST, Scripts CLI e Operação de Containers

Este documento descreve os endpoints do servidor FastAPI (`server.py`), os comandos operacionais via terminal e o gerenciamento de imagens Docker.

---

## 1. Endpoints da API REST (`server.py`)

O servidor FastAPI roda na porta `8000` (`http://localhost:8000`) e expõe os seguintes contratos:

| Método | Rota | Descrição |
| :---: | :--- | :--- |
| `GET` | `/api/health` | Verifica a disponibilidade do serviço backend. |
| `GET` | `/api/estatisticas` | Retorna totais agregados de produtos (`concluidos`, `parciais`, `pendentes`, `falhas`) e contadores por canal. |
| `GET` | `/api/produtos` | Lista produtos com paginação (`pagina`, `limite`) e filtros (`status`, `busca`, `lista`). |
| `GET` | `/api/produtos/{item_id}` | Retorna os dados do produto, o estado dos 6 canais e o histórico de logs (`historico_logs`). |
| `DELETE` | `/api/produtos/{item_id}` | Remove um produto e seus registros associados do SQLite. |
| `POST` | `/api/produtos/upload-csv` | Recebe o conteúdo de uma planilha CSV e insere novos produtos de forma idempotente. |
| `POST` | `/api/produtos/adicionar-link` | Extrai metadados de um link de afiliado ou produto (ex.: Mercado Livre `meli.la`, Shopee) e cadastra o produto no banco. |
| `GET` | `/api/produtos/envio-status` | Retorna o estado em tempo real da fila de publicação em andamento (`ativo`, `item_id`, `canal_atual`, `etapa_label`, `indice_atual`, `total_itens`). |
| `POST` | `/api/produtos/{item_id}/reenviar` | Dispara em background o reenvio cirúrgico dos canais pendentes/falhos de um produto. |
| `POST` | `/api/produtos/reenviar-falhas` | Dispara em background o reenvio em lote de todos os produtos incompletos. |
| `POST` | `/api/produtos/enviar-selecionados` | Dispara em background o envio/reenvio de uma lista de `item_ids`. |
| `POST` | `/api/produtos/excluir-selecionados` | Exclui em lote múltiplos `item_ids`. |
| `GET` | `/api/listas` | Lista todas as listas temáticas e a contagem de produtos vinculados. |
| `POST` | `/api/listas` | Cria uma nova lista temática. |
| `DELETE` | `/api/listas/{nome}` | Exclui uma lista temática (desvinculando ou mantendo os produtos). |
| `GET` | `/api/integracoes/status` | Valida a presença e conectividade das credenciais de WhatsApp, Facebook, Instagram e Shopee. |
| `GET` | `/api/conversoes` | Lista conversões e comissões sincronizadas da Shopee Affiliate Open API. |
| `POST` | `/api/conversoes/sincronizar` | Sincroniza o relatório de conversões da Shopee para o período informado. |

---

## 2. Scripts de Linha de Comando (CLI)

### Publicação de Catálogo CSV (`publicar.py`)
```bash
# Publicação real com intervalo de 60 segundos entre produtos
python3 publicar.py produtos/teste.csv --delay 60

# Simulação (Dry-Run) sem chamadas externas
python3 publicar.py produtos/teste.csv --dry-run

# Relatório de status no terminal
python3 publicar.py --status
```

### Reprocessamento Cirúrgico de Pendências (`reenviar_falhas.py`)
```bash
# Reenviar todos os produtos com canais pendentes ou com falha
python3 reenviar_falhas.py

# Reenviar exclusivamente um Item ID específico
python3 reenviar_falhas.py --item-id 46560301686
```

### Geração Isolada de Artes (`instagran/tratarParaInstagran.py`)
```bash
# Renderizar Stories, Post e Reels (.png e .mp4) para um produto específico
python3 instagran/tratarParaInstagran.py "https://shopee.com.br/product/..." --item-id 46560301686 --price "49,90"
```

---

## 3. Operação de Containers e Publicação Docker Hub

### Padronização Obrigatória
- **Rede Externa:** todos os containers devem utilizar a rede `containers` (`docker network create containers`).
- **Timezone:** todos os serviços devem operar com `TZ=America/Cuiaba`.

### Subida do Ambiente Local (`subir_containers.sh`)
```bash
./subir_containers.sh
```
- Backend disponível em `http://localhost:8000` (com volume mapeado e `--reload` ativo).
- Frontend Angular disponível em `http://localhost:4200`.

### Build e Push Multi-Arquitetura (`publicar_docker.sh`)
Utiliza as variáveis `DOCKER_USER`, `DOCKER_PASS` e `DOCKER_VERSION` definidas no `.env` para compilar e publicar imagens `linux/amd64` e `linux/arm64` no repositório `allinefreire/afiliados`:
```bash
./publicar_docker.sh
```
Tags geradas e enviadas:
- `allinefreire/afiliados:<DOCKER_VERSION>` e `allinefreire/afiliados:latest`
- `allinefreire/afiliados:<DOCKER_VERSION>-backend` e `allinefreire/afiliados:latest-backend`
- `allinefreire/afiliados:<DOCKER_VERSION>-frontend` e `allinefreire/afiliados:latest-frontend`

