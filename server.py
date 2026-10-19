#!/usr/bin/env python3
"""Servidor REST API FastAPI para o ecossistema Afiliados Multi-Channel Hub."""
import asyncio
import csv
import io
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from shopee.client import load_env
from facebook.client import FacebookPageClient
from instagran.client import InstagramClient
from whatsapp.client import ZApiClient
from db.controle import (
    inicializar_banco,
    obter_resumo_estatisticas,
    listar_produtos_paginado,
    obter_produto,
    obter_historico_logs_produto,
    excluir_produto,
    excluir_lote_produtos,
    inserir_lote_produtos,
    CANAIS_OBRIGATORIOS,
)
from reenviar_falhas import reenviar_produto_pendente

# Inicializa variáveis de ambiente e banco SQLite
load_env()
inicializar_banco()

app = FastAPI(
    title="Afiliados Multi-Channel Hub API",
    description="API para orquestração de produtos, upload de ofertas e publicações multi-canal.",
    version="1.0.0",
)

# Habilita CORS para o frontend Angular
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UploadCSVRequest(BaseModel):
    nome_arquivo: str
    conteudo: str


class ReenvioRequest(BaseModel):
    dry_run: bool = False


@app.get("/api/health")
def health_check():
    """Verifica a saúde operacional básica do backend."""
    return {"status": "ok", "servico": "Afiliados Hub Backend"}


@app.get("/api/estatisticas")
def get_estatisticas():
    """Retorna indicadores agregados para o dashboard do frontend."""
    return obter_resumo_estatisticas()


@app.get("/api/produtos")
def get_produtos(
    pagina: int = Query(1, ge=1, description="Número da página"),
    limite: int = Query(20, ge=1, le=100, description="Itens por página"),
    status: Optional[str] = Query(None, description="Filtro por status geral"),
    busca: Optional[str] = Query(None, description="Busca por ID ou nome"),
):
    """Retorna lista paginada de produtos com seus respectivos status por canal."""
    status_str = status if isinstance(status, str) else None
    busca_str = busca if isinstance(busca, str) else None
    return listar_produtos_paginado(
        pagina=pagina if isinstance(pagina, int) else 1,
        limite=limite if isinstance(limite, int) else 20,
        status_filtro=status_str,
        busca=busca_str,
    )


@app.get("/api/produtos/{item_id}")
def get_detalhe_produto(item_id: str):
    """Retorna detalhes completos de um produto e seu histórico de logs."""
    produto = obter_produto(item_id)
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    
    logs = obter_historico_logs_produto(item_id)
    return {
        "produto": produto,
        "logs": logs,
    }


@app.delete("/api/produtos/{item_id}")
def delete_produto(item_id: str):
    """Exclui um produto do banco de dados."""
    sucesso = excluir_produto(item_id)
    if not sucesso:
        raise HTTPException(status_code=404, detail="Produto não encontrado para exclusão")
    return {"sucesso": True, "mensagem": f"Produto {item_id} excluído com sucesso"}


@app.post("/api/produtos/upload-csv")
def upload_csv_produtos(payload: UploadCSVRequest):
    """Processa o upload de um arquivo CSV de ofertas e efetua a carga no banco."""
    conteudo = payload.conteudo.strip()
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo CSV vazio")

    linhas = [l for l in conteudo.splitlines() if l.strip()]
    if not linhas:
        raise HTTPException(status_code=400, detail="Arquivo CSV vazio")

    primeira_linha = linhas[0]
    delimitador = ";" if (";" in primeira_linha and "," not in primeira_linha) else ","

    f = io.StringIO("\n".join(linhas))
    reader = csv.reader(f, delimiter=delimitador)

    try:
        header = [h.strip().replace('"', '').replace("'", "") for h in next(reader)]
    except StopIteration:
        raise HTTPException(status_code=400, detail="Cabeçalho do CSV ausente")

    produtos_para_inserir = []
    for row in reader:
        if not row:
            continue
        d = dict(zip(header, [c.strip().replace('"', '').replace("'", "") for c in row]))
        produtos_para_inserir.append(d)

    resultado = inserir_lote_produtos(produtos_para_inserir)
    return resultado


def _executar_reenvio_background(item_id: str, dry_run: bool = False):
    """Executa a rotina de reenvio em segundo plano para não bloquear a requisição HTTP."""
    try:
        produto = obter_produto(item_id)
        if not produto:
            return

        fb = FacebookPageClient() if not dry_run else None
        ig = InstagramClient() if not dry_run else None
        wa = ZApiClient() if not dry_run else None

        reenviar_produto_pendente(produto, fb, ig, wa, dry_run=dry_run)
    except Exception as e:
        print(f"Erro em background ao reenviar item {item_id}: {e}")


@app.post("/api/produtos/{item_id}/reenviar")
def reenviar_produto_rota(
    item_id: str,
    payload: ReenvioRequest,
    background_tasks: BackgroundTasks,
):
    """Dispara o reenvio das publicações pendentes de um produto específico."""
    produto = obter_produto(item_id)
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    background_tasks.add_task(_executar_reenvio_background, item_id, payload.dry_run)
    return {
        "sucesso": True,
        "mensagem": f"Reenvio do produto {item_id} iniciado em segundo plano.",
        "item_id": item_id,
    }


def _executar_reenvio_lote_background(dry_run: bool = False):
    """Executa reenvio de todos os produtos pendentes em lote."""
    from db.controle import obter_produtos_para_reprocessamento
    produtos = obter_produtos_para_reprocessamento()
    if not produtos:
        return

    try:
        fb = FacebookPageClient() if not dry_run else None
        ig = InstagramClient() if not dry_run else None
        wa = ZApiClient() if not dry_run else None

        for prod in produtos:
            reenviar_produto_pendente(prod, fb, ig, wa, dry_run=dry_run)
    except Exception as e:
        print(f"Erro em lote ao reenviar pendências: {e}")


@app.post("/api/produtos/reenviar-falhas")
def reenviar_todos_falhas(
    payload: ReenvioRequest,
    background_tasks: BackgroundTasks,
):
    """Dispara o reenvio de todas as publicações pendentes do banco."""
    background_tasks.add_task(_executar_reenvio_lote_background, payload.dry_run)
    return {
        "sucesso": True,
        "mensagem": "Rotina de reenvio em lote iniciada com sucesso.",
    }


class EnviarSelecionadosRequest(BaseModel):
    item_ids: list[str]
    dry_run: bool = False


def _executar_reenvio_selecionados_background(item_ids: list[str], dry_run: bool = False):
    """Executa o reenvio dos produtos selecionados."""
    try:
        fb = FacebookPageClient() if not dry_run else None
        ig = InstagramClient() if not dry_run else None
        wa = ZApiClient() if not dry_run else None

        for item_id in item_ids:
            prod = obter_produto(item_id)
            if prod:
                reenviar_produto_pendente(prod, fb, ig, wa, dry_run=dry_run)
    except Exception as e:
        print(f"Erro ao processar envio dos selecionados: {e}")


@app.post("/api/produtos/enviar-selecionados")
def enviar_produtos_selecionados(
    payload: EnviarSelecionadosRequest,
    background_tasks: BackgroundTasks,
):
    """Dispara o envio/reenvio dos produtos selecionados."""
    if not payload.item_ids:
        raise HTTPException(status_code=400, detail="Nenhum produto selecionado")

    background_tasks.add_task(_executar_reenvio_selecionados_background, payload.item_ids, payload.dry_run)
    return {
        "sucesso": True,
        "mensagem": f"Envio de {len(payload.item_ids)} produto(s) selecionado(s) iniciado em segundo plano.",
        "total": len(payload.item_ids),
    }


class ExcluirSelecionadosRequest(BaseModel):
    item_ids: list[str]


@app.post("/api/produtos/excluir-selecionados")
def excluir_produtos_selecionados(payload: ExcluirSelecionadosRequest):
    """Exclui múltiplos produtos selecionados pelo usuário."""
    if not payload.item_ids:
        raise HTTPException(status_code=400, detail="Nenhum produto selecionado para exclusão")

    total = excluir_lote_produtos(payload.item_ids)
    return {
        "sucesso": True,
        "total_excluidos": total,
        "mensagem": f"{total} produto(s) excluído(s) com sucesso.",
    }


@app.get("/api/integracoes/status")
def get_integracoes_status():
    """Consulta credenciais e faz validação rápida da conectividade com os serviços externos."""
    status_dict = {
        "whatsapp": {"configurado": False, "mensagem": ""},
        "facebook": {"configurado": False, "mensagem": ""},
        "instagram": {"configurado": False, "mensagem": ""},
        "shopee": {"configurado": False, "mensagem": ""},
    }

    # WhatsApp Z-API
    try:
        wa_id = os.environ.get("ZAPI_ID")
        wa_token = os.environ.get("ZAPI_TOKEN")
        if wa_id and wa_token:
            status_dict["whatsapp"] = {"configurado": True, "mensagem": "Instância configurada"}
        else:
            status_dict["whatsapp"] = {"configurado": False, "mensagem": "Credenciais ZAPI ausentes"}
    except Exception as e:
        status_dict["whatsapp"] = {"configurado": False, "mensagem": str(e)}

    # Facebook
    try:
        page_id = os.environ.get("META_PAGE_ID")
        page_token = os.environ.get("META_PAGE_TOKEN")
        if page_id and page_token:
            status_dict["facebook"] = {"configurado": True, "mensagem": f"Página {page_id} configurada"}
        else:
            status_dict["facebook"] = {"configurado": False, "mensagem": "Credenciais Meta ausentes"}
    except Exception as e:
        status_dict["facebook"] = {"configurado": False, "mensagem": str(e)}

    # Instagram
    try:
        ig_id = os.environ.get("INSTAGRAM_ACCOUNT_ID")
        if ig_id and page_token:
            status_dict["instagram"] = {"configurado": True, "mensagem": f"Conta {ig_id} configurada"}
        else:
            status_dict["instagram"] = {"configurado": False, "mensagem": "Conta Instagram ausente"}
    except Exception as e:
        status_dict["instagram"] = {"configurado": False, "mensagem": str(e)}

    # Shopee
    try:
        app_id = os.environ.get("SHOPEE_AFFILIATE_APP_ID")
        secret = os.environ.get("SHOPEE_AFFILIATE_SECRET")
        if app_id and secret:
            status_dict["shopee"] = {"configurado": True, "mensagem": "App ID e Secret configurados"}
        else:
            status_dict["shopee"] = {"configurado": False, "mensagem": "Credenciais Shopee ausentes"}
    except Exception as e:
        status_dict["shopee"] = {"configurado": False, "mensagem": str(e)}

    return status_dict


@app.get("/api/artes/{data}/{item_id}/{arquivo}")
def get_arte_imagem(data: str, item_id: str, arquivo: str):
    """Serve as imagens de artes geradas armazenadas em db/img."""
    caminho = ROOT / "db" / "img" / data / item_id / arquivo
    if not caminho.exists() or not caminho.is_file():
        raise HTTPException(status_code=404, detail="Imagem não encontrada")
    return FileResponse(caminho)


@app.get("/")
def get_frontend_root():
    """Serve a aplicação frontend do Afiliados Hub."""
    preview_file = ROOT / "frontend" / "index_preview.html"
    if preview_file.exists():
        return FileResponse(preview_file)
    return {"mensagem": "Afiliados Hub Backend operacional. Acesse /docs para Swagger."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

