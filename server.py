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

from shopee.client import load_env, ShopeeAffiliateClient
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
    registrar_produto,
    salvar_conversoes_shopee,
    obter_resumo_conversoes,
    listar_conversoes,
    garantir_lista,
    listar_todas_listas,
    excluir_lista,
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


class CriarListaRequest(BaseModel):
    nome: str


class AdicionarLinkRequest(BaseModel):
    url: str
    lista: Optional[str] = None
    item_name: Optional[str] = None
    price: Optional[str] = None


ENVIO_ATUAL_STATUS = {
    "ativo": False,
    "item_id_atual": None,
    "item_name_atual": None,
    "canal_atual": None,
    "descricao_etapa": None,
    "processados": 0,
    "total": 0,
}


def _atualizar_envio_status(
    ativo: bool,
    item_id: Optional[str] = None,
    item_name: Optional[str] = None,
    canal: Optional[str] = None,
    descricao: Optional[str] = None,
    processados: Optional[int] = None,
    total: Optional[int] = None,
) -> None:
    ENVIO_ATUAL_STATUS["ativo"] = ativo
    ENVIO_ATUAL_STATUS["item_id_atual"] = item_id
    ENVIO_ATUAL_STATUS["item_name_atual"] = item_name
    ENVIO_ATUAL_STATUS["canal_atual"] = canal
    ENVIO_ATUAL_STATUS["descricao_etapa"] = descricao
    if processados is not None:
        ENVIO_ATUAL_STATUS["processados"] = processados
    if total is not None:
        ENVIO_ATUAL_STATUS["total"] = total


@app.get("/api/health")
def health_check():
    """Verifica a saúde operacional básica do backend."""
    return {"status": "ok", "servico": "Afiliados Hub Backend"}


@app.get("/api/estatisticas")
def get_estatisticas():
    """Retorna indicadores agregados para o dashboard do frontend."""
    return obter_resumo_estatisticas()


@app.get("/api/listas")
def get_listas():
    """Retorna todas as listas temáticas cadastradas e a quantidade de produtos associados."""
    return listar_todas_listas()


@app.post("/api/listas")
def post_criar_lista(payload: CriarListaRequest):
    """Cria ou garante a existência de uma lista temática."""
    nome = str(payload.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="O nome da lista não pode ser vazio.")
    nome_criado = garantir_lista(nome)
    return {"sucesso": True, "nome": nome_criado}


@app.delete("/api/listas/{nome}")
def delete_lista(nome: str, desvincular: bool = Query(True)):
    """Remove uma lista temática cadastrada."""
    sucesso = excluir_lista(nome, desvincular_produtos=desvincular)
    return {"sucesso": sucesso}


@app.get("/api/produtos")
def get_produtos(
    pagina: int = Query(1, ge=1, description="Número da página"),
    limite: int = Query(20, ge=1, le=100, description="Itens por página"),
    status: Optional[str] = Query(None, description="Filtro por status geral"),
    busca: Optional[str] = Query(None, description="Busca por ID ou nome"),
    lista: Optional[str] = Query(None, description="Filtro por lista temática"),
):
    """Retorna lista paginada de produtos com seus respectivos status por canal."""
    status_str = status if isinstance(status, str) else None
    busca_str = busca if isinstance(busca, str) else None
    lista_str = lista if isinstance(lista, str) else None
    return listar_produtos_paginado(
        pagina=pagina if isinstance(pagina, int) else 1,
        limite=limite if isinstance(limite, int) else 20,
        status_filtro=status_str,
        busca=busca_str,
        lista_filtro=lista_str,
    )


@app.get("/api/produtos/envio-status")
def get_envio_status():
    """Retorna o estado em tempo real do envio/reenvio em andamento para auto-refresh do painel."""
    return ENVIO_ATUAL_STATUS


@app.post("/api/produtos/adicionar-link")
def post_adicionar_produto_por_link(payload: AdicionarLinkRequest):
    """Extrai metadados de um link de afiliado/produto (ex: https://meli.la/2e9SRc8) e cadastra no banco."""
    url_str = str(payload.url or "").strip()
    if not url_str or not (url_str.startswith("http://") or url_str.startswith("https://")):
        raise HTTPException(status_code=400, detail="Informe uma URL válida iniciando com http:// ou https://")

    try:
        from produtos.reader import extrair_produto_de_link
        dados = extrair_produto_de_link(url_str)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Não foi possível extrair os dados do link: {e}")

    if payload.item_name and payload.item_name.strip():
        dados["item_name"] = payload.item_name.strip()
    if payload.price and payload.price.strip():
        dados["price"] = payload.price.strip().replace("R$", "").strip()

    lista_nome = str(payload.lista).strip() if payload.lista and payload.lista.strip() else None
    if lista_nome and lista_nome not in ("TODAS", "SEM_LISTA"):
        garantir_lista(lista_nome)
        dados["lista"] = lista_nome

    registrar_produto(dados, ignorar_se_existir=False)
    prod_salvo = obter_produto(dados["item_id"])
    return {
        "sucesso": True,
        "mensagem": f"Produto '{dados.get('item_name')}' incluído com sucesso!",
        "produto": prod_salvo or dados,
    }


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

        _atualizar_envio_status(
            True,
            item_id=item_id,
            item_name=produto.get("item_name"),
            canal="iniciando",
            descricao="Preparando publicação nos canais...",
            processados=0,
            total=1,
        )

        fb = FacebookPageClient() if not dry_run else None
        ig = InstagramClient() if not dry_run else None
        wa = ZApiClient() if not dry_run else None

        def _on_etapa(iid: str, canal: str, desc: str) -> None:
            _atualizar_envio_status(
                True,
                item_id=iid,
                item_name=produto.get("item_name"),
                canal=canal,
                descricao=desc,
                processados=0,
                total=1,
            )

        reenviar_produto_pendente(produto, fb, ig, wa, dry_run=dry_run, on_etapa=_on_etapa)
    except Exception as e:
        print(f"Erro em background ao reenviar item {item_id}: {e}")
    finally:
        _atualizar_envio_status(False, processados=1, total=1)


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

    _atualizar_envio_status(
        True,
        item_id=item_id,
        item_name=produto.get("item_name"),
        canal="fila",
        descricao="Iniciando envio do produto...",
        processados=0,
        total=1,
    )
    background_tasks.add_task(_executar_reenvio_background, item_id, payload.dry_run)
    return {
        "sucesso": True,
        "mensagem": f"Envio do produto {item_id} iniciado em segundo plano.",
        "item_id": item_id,
    }


def _executar_reenvio_lote_background(dry_run: bool = False):
    """Executa reenvio de todos os produtos pendentes em lote."""
    from db.controle import obter_produtos_para_reprocessamento
    produtos = obter_produtos_para_reprocessamento()
    if not produtos:
        _atualizar_envio_status(False, processados=0, total=0)
        return

    total = len(produtos)
    try:
        fb = FacebookPageClient() if not dry_run else None
        ig = InstagramClient() if not dry_run else None
        wa = ZApiClient() if not dry_run else None

        for idx, prod in enumerate(produtos):
            nome_prod = prod.get("item_name", prod.get("item_id"))
            def _on_etapa(iid: str, canal: str, desc: str, i=idx, np=nome_prod) -> None:
                _atualizar_envio_status(
                    True,
                    item_id=iid,
                    item_name=np,
                    canal=canal,
                    descricao=desc,
                    processados=i,
                    total=total,
                )
            reenviar_produto_pendente(prod, fb, ig, wa, dry_run=dry_run, on_etapa=_on_etapa)
    except Exception as e:
        print(f"Erro em lote ao reenviar pendências: {e}")
    finally:
        _atualizar_envio_status(False, processados=total, total=total)


@app.post("/api/produtos/reenviar-falhas")
def reenviar_todos_falhas(
    payload: ReenvioRequest,
    background_tasks: BackgroundTasks,
):
    """Dispara o reenvio de todas as publicações pendentes do banco."""
    _atualizar_envio_status(True, canal="fila", descricao="Iniciando reenvio em lote...", processados=0, total=1)
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
    total = len(item_ids)
    try:
        fb = FacebookPageClient() if not dry_run else None
        ig = InstagramClient() if not dry_run else None
        wa = ZApiClient() if not dry_run else None

        for idx, item_id in enumerate(item_ids):
            prod = obter_produto(item_id)
            if prod:
                nome_prod = prod.get("item_name", item_id)
                def _on_etapa(iid: str, canal: str, desc: str, i=idx, np=nome_prod) -> None:
                    _atualizar_envio_status(
                        True,
                        item_id=iid,
                        item_name=np,
                        canal=canal,
                        descricao=desc,
                        processados=i,
                        total=total,
                    )
                reenviar_produto_pendente(prod, fb, ig, wa, dry_run=dry_run, on_etapa=_on_etapa)
    except Exception as e:
        print(f"Erro ao processar envio dos selecionados: {e}")
    finally:
        _atualizar_envio_status(False, processados=total, total=total)


@app.post("/api/produtos/enviar-selecionados")
def enviar_produtos_selecionados(
    payload: EnviarSelecionadosRequest,
    background_tasks: BackgroundTasks,
):
    """Dispara o envio/reenvio dos produtos selecionados."""
    if not payload.item_ids:
        raise HTTPException(status_code=400, detail="Nenhum produto selecionado")

    _atualizar_envio_status(
        True,
        item_id=payload.item_ids[0],
        canal="fila",
        descricao=f"Iniciando envio de {len(payload.item_ids)} produto(s) selecionado(s)...",
        processados=0,
        total=len(payload.item_ids),
    )
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
        from instagran.client import InstagramClient
        ig_client = InstagramClient()
        status_dict["instagram"] = {
            "configurado": True,
            "mensagem": f"Conta {ig_client.account_id} vinculada e pronta",
        }
    except Exception as e:
        status_dict["instagram"] = {
            "configurado": False,
            "mensagem": f"Instagram não conectado: {e}",
        }

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


class ShopeeImportarOfertasRequest(BaseModel):
    itens: list[dict]
    lista: Optional[str] = None


class ShopeeGerarLinkRequest(BaseModel):
    origin_url: str
    canal: Optional[str] = "whatsapp"
    sub_ids: Optional[list[str]] = None


@app.get("/api/shopee/ofertas")
def get_shopee_ofertas(
    keyword: Optional[str] = Query(None, description="Palavra-chave para busca"),
    sort_type: int = Query(2, description="Ordenação (1=relevância, 2=vendas, 5=comissão)"),
    page: int = Query(1, ge=1, description="Número da página"),
    limit: int = Query(20, ge=1, le=50, description="Limite de itens por página"),
    item_id: Optional[int] = Query(None, description="Filtrar por Item ID"),
):
    """Consulta ofertas elegíveis a comissão via Shopee Affiliate Open API."""
    try:
        client = ShopeeAffiliateClient()
        resultado = client.buscar_ofertas(
            keyword=keyword,
            sort_type=sort_type,
            page=page,
            limit=limit,
            item_id=item_id,
        )
        return resultado.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar API Shopee: {e}")


@app.post("/api/shopee/importar-ofertas")
def post_shopee_importar_ofertas(payload: ShopeeImportarOfertasRequest):
    """Importa produtos obtidos via API da Shopee diretamente para o banco de dados do Hub."""
    if not payload.itens:
        raise HTTPException(status_code=400, detail="Nenhum item informado para importação")

    lista_nome = str(payload.lista).strip() if payload.lista else None
    if lista_nome:
        garantir_lista(lista_nome)

    total_importados = 0
    for it in payload.itens:
        item_id = str(it.get("item_id") or it.get("itemId") or "").strip()
        if not item_id:
            continue
        prod_data = {
            "item_id": item_id,
            "item_name": it.get("product_name") or it.get("productName") or f"Produto {item_id}",
            "offer_link": it.get("offer_link") or it.get("offerLink") or "",
            "product_link": it.get("product_link") or it.get("productLink") or "",
            "price": str(it.get("price") or "0"),
            "image_url": it.get("image_url") or it.get("imageUrl") or "",
            "commission_rate": str(it.get("commission_rate") or it.get("commissionRate") or ""),
            "sales": int(it.get("sales") or 0),
            "rating_star": float(it.get("rating_star") or it.get("ratingStar") or 0.0),
            "lista": lista_nome,
        }
        if registrar_produto(prod_data, ignorar_se_existir=False):
            total_importados += 1

    msg_complemento = f" na lista '{lista_nome}'" if lista_nome else ""
    return {
        "sucesso": True,
        "total_importados": total_importados,
        "lista": lista_nome,
        "mensagem": f"{total_importados} produto(s) importado(s) com sucesso para o banco de dados{msg_complemento}.",
    }


@app.get("/api/shopee/conversoes")
def get_shopee_conversoes(limite: int = Query(50, ge=1, le=200)):
    """Retorna o resumo consolidado e histórico de conversões sincronizadas da Shopee."""
    resumo = obter_resumo_conversoes()
    lista = listar_conversoes(limite=limite)
    return {
        "resumo": resumo,
        "conversoes": lista,
    }


@app.post("/api/shopee/sincronizar-conversoes")
def post_sincronizar_conversoes(limit: int = Query(50, ge=1, le=100)):
    """Busca as conversões mais recentes via Shopee GraphQL e salva no banco de dados."""
    try:
        client = ShopeeAffiliateClient()
        itens = client.obter_relatorio_conversoes(limit=limit)
        dados = [it.to_dict() for it in itens]
        total = salvar_conversoes_shopee(dados)
        return {
            "sucesso": True,
            "total_sincronizados": total,
            "mensagem": f"{total} registro(s) de conversão reconciliado(s) no banco.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao sincronizar conversões: {e}")


@app.post("/api/shopee/gerar-link")
def post_gerar_link(payload: ShopeeGerarLinkRequest):
    """Gera link encurtado parametrizado com subId específico de canal."""
    if not payload.origin_url:
        raise HTTPException(status_code=400, detail="origin_url é obrigatório")
    try:
        client = ShopeeAffiliateClient()
        if payload.sub_ids:
            link = client.gerar_link_rastreado(payload.origin_url, payload.sub_ids)
        else:
            link = client.gerar_link_canal(payload.origin_url, payload.canal or "whatsapp")
        if not link:
            raise HTTPException(status_code=500, detail="Não foi possível gerar link rastreado")
        return {"sucesso": True, "link_rastreado": link}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/artes/{data}/{item_id}/{arquivo}")
def get_arte_imagem(data: str, item_id: str, arquivo: str):
    """Serve as imagens de artes geradas armazenadas em db/img."""
    caminho = ROOT / "db" / "img" / data / item_id / arquivo
    if not caminho.exists() or not caminho.is_file():
        raise HTTPException(status_code=404, detail="Imagem não encontrada")
    return FileResponse(caminho)


@app.get("/instagran/templates/{arquivo}")
@app.get("/instgran/templates/{arquivo}")
def get_template_asset(arquivo: str):
    """Serve arquivos estáticos da pasta instagran/templates (como linkolandia.png)."""
    nome_seguro = Path(arquivo).name
    caminho = ROOT / "instagran" / "templates" / nome_seguro
    if not caminho.exists() or not caminho.is_file():
        raise HTTPException(status_code=404, detail="Recurso não encontrado")
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

