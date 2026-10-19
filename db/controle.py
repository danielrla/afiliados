"""Módulo de controle de publicações e idempotência via SQLite."""
import datetime
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "db"
DB_PATH = DB_DIR / "publicacoes.db"

CANAIS_OBRIGATORIOS = [
    "whatsapp",
    "facebook",
    "instagram_stories",
    "instagram_post",
    "instagram_reels",
]


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Retorna uma conexão SQLite com suporte a dicionário nas linhas."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_banco(db_path: Path = DB_PATH) -> None:
    """Cria a estrutura de tabelas se ainda não existir e aplica migrações incrementais."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Tabela principal de produtos
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            item_id TEXT PRIMARY KEY,
            item_name TEXT NOT NULL,
            offer_link TEXT NOT NULL,
            product_link TEXT,
            price TEXT,
            image_url TEXT,
            codigo_artes TEXT,
            pasta_artes TEXT,
            status_geral TEXT DEFAULT 'PENDENTE',
            criado_em TEXT,
            atualizado_em TEXT
        );
        """)

        # Tabela de status atual por canal (uma linha por produto e canal)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS canais_status (
            item_id TEXT,
            canal TEXT,
            status TEXT NOT NULL, -- 'SUCESSO', 'FALHA', 'PENDENTE'
            id_externo TEXT,
            mensagem_erro TEXT,
            tentativas INTEGER DEFAULT 1,
            atualizado_em TEXT,
            PRIMARY KEY (item_id, canal),
            FOREIGN KEY (item_id) REFERENCES produtos(item_id) ON DELETE CASCADE
        );
        """)

        # Tabela de log histórico cumulativo para auditoria
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT,
            canal TEXT,
            status TEXT,
            id_externo TEXT,
            mensagem_erro TEXT,
            caminho_imagem TEXT,
            data_envio TEXT,
            FOREIGN KEY (item_id) REFERENCES produtos(item_id)
        );
        """)

        # Migrações incrementais seguras para bancos existentes
        cursor.execute("PRAGMA table_info(historico_logs);")
        cols_logs = [r["name"] for r in cursor.fetchall()]
        if "caminho_imagem" not in cols_logs:
            cursor.execute("ALTER TABLE historico_logs ADD COLUMN caminho_imagem TEXT;")

        cursor.execute("PRAGMA table_info(produtos);")
        cols_prod = [r["name"] for r in cursor.fetchall()]
        if "pasta_artes" not in cols_prod:
            cursor.execute("ALTER TABLE produtos ADD COLUMN pasta_artes TEXT;")
        if "image_url" not in cols_prod:
            cursor.execute("ALTER TABLE produtos ADD COLUMN image_url TEXT;")

        conn.commit()


def registrar_produto(produto: dict, db_path: Path = DB_PATH, ignorar_se_existir: bool = True) -> bool:
    """
    Insere o produto no banco.
    Se ignorar_se_existir for True e o Item ID já constar na tabela produtos, ignora a inclusão e retorna False.
    Retorna True se o produto for recém-inserido ou atualizado.
    """
    inicializar_banco(db_path)
    agora = datetime.datetime.now().isoformat()
    item_id = str(produto.get("item_id", "")).strip()
    if not item_id:
        return False
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if ignorar_se_existir:
            cursor.execute("SELECT 1 FROM produtos WHERE item_id = ? LIMIT 1;", (item_id,))
            if cursor.fetchone():
                return False

        cursor.execute("""
        INSERT INTO produtos (item_id, item_name, offer_link, product_link, price, image_url, codigo_artes, pasta_artes, criado_em, atualizado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            item_name=excluded.item_name,
            offer_link=excluded.offer_link,
            product_link=excluded.product_link,
            price=excluded.price,
            image_url=COALESCE(excluded.image_url, produtos.image_url),
            codigo_artes=COALESCE(excluded.codigo_artes, produtos.codigo_artes),
            pasta_artes=COALESCE(excluded.pasta_artes, produtos.pasta_artes),
            atualizado_em=excluded.atualizado_em;
        """, (
            item_id,
            produto.get("item_name", ""),
            produto.get("offer_link", ""),
            produto.get("product_link", ""),
            produto.get("price", ""),
            produto.get("image_url"),
            produto.get("codigo_artes"),
            produto.get("pasta_artes"),
            agora,
            agora,
        ))
        conn.commit()
        return True


def atualizar_imagem_produto(item_id: str, image_url: str, db_path: Path = DB_PATH) -> None:
    """Salva ou atualiza a URL da imagem oficial do produto no banco."""
    inicializar_banco(db_path)
    agora = datetime.datetime.now().isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE produtos SET
            image_url = ?,
            atualizado_em = ?
        WHERE item_id = ?;
        """, (str(image_url), agora, str(item_id)))
        conn.commit()



def atualizar_codigo_artes(item_id: str, codigo_artes: str, pasta_artes: str | None = None, db_path: Path = DB_PATH) -> None:
    """Salva o código numérico e a pasta das artes geradas para o produto."""
    agora = datetime.datetime.now().isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE produtos SET
            codigo_artes = ?,
            pasta_artes = COALESCE(?, pasta_artes),
            atualizado_em = ?
        WHERE item_id = ?;
        """, (codigo_artes, pasta_artes, agora, str(item_id)))
        conn.commit()


def obter_status_canais(item_id: str, db_path: Path = DB_PATH) -> dict[str, str]:
    """Retorna um dicionário com o status de cada canal para o produto (ex: {'whatsapp': 'SUCESSO'})."""
    inicializar_banco(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT canal, status FROM canais_status WHERE item_id = ?", (str(item_id),))
        rows = cursor.fetchall()
        return {r["canal"]: r["status"] for r in rows}


def registrar_resultado_canal(
    item_id: str,
    canal: str,
    status: str,
    id_externo: str | None = None,
    mensagem_erro: str | None = None,
    caminho_imagem: str | None = None,
    db_path: Path = DB_PATH,
) -> None:
    """Atualiza o resultado de envio de um canal, grava o caminho da mídia no log e recalcula o status geral."""
    inicializar_banco(db_path)
    agora = datetime.datetime.now().isoformat()
    item_id_str = str(item_id)
    caminho_img_str = str(caminho_imagem) if caminho_imagem else None

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Atualiza ou insere o status do canal incrementando o número de tentativas
        cursor.execute("""
        INSERT INTO canais_status (item_id, canal, status, id_externo, mensagem_erro, tentativas, atualizado_em)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(item_id, canal) DO UPDATE SET
            status = excluded.status,
            id_externo = COALESCE(excluded.id_externo, canais_status.id_externo),
            mensagem_erro = excluded.mensagem_erro,
            tentativas = canais_status.tentativas + 1,
            atualizado_em = excluded.atualizado_em;
        """, (item_id_str, canal, status, id_externo, mensagem_erro, agora))

        # Adiciona no log de auditoria com o caminho da imagem
        cursor.execute("""
        INSERT INTO historico_logs (item_id, canal, status, id_externo, mensagem_erro, caminho_imagem, data_envio)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (item_id_str, canal, status, id_externo, mensagem_erro, caminho_img_str, agora))

        # Recalcula o status_geral do produto
        cursor.execute("SELECT status FROM canais_status WHERE item_id = ?", (item_id_str,))
        statuses = [r["status"] for r in cursor.fetchall()]

        if len(statuses) >= len(CANAIS_OBRIGATORIOS) and all(s == "SUCESSO" for s in statuses):
            status_geral = "CONCLUIDO"
        elif any(s == "SUCESSO" for s in statuses):
            status_geral = "PARCIAL"
        else:
            status_geral = "FALHA"

        cursor.execute("""
        UPDATE produtos SET status_geral = ?, atualizado_em = ? WHERE item_id = ?;
        """, (status_geral, agora, item_id_str))

        conn.commit()


def obter_produto(item_id: str, db_path: Path = DB_PATH) -> dict | None:
    """Busca um produto específico pelo seu Item Id."""
    inicializar_banco(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM produtos WHERE item_id = ?;", (str(item_id),))
        row = cursor.fetchone()
        if not row:
            return None
        prod = dict(row)
        prod["canais_status"] = obter_status_canais(prod["item_id"], db_path)
        return prod


def obter_produtos_para_reprocessamento(db_path: Path = DB_PATH) -> list[dict]:
    """Retorna produtos cadastrados que possuem pelo menos um canal não concluído com SUCESSO."""
    inicializar_banco(db_path)
    produtos = []
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM produtos WHERE status_geral != 'CONCLUIDO' ORDER BY criado_em ASC;
        """)
        for row in cursor.fetchall():
            prod = dict(row)
            prod["canais_status"] = obter_status_canais(prod["item_id"], db_path)
            produtos.append(prod)
    return produtos


def gerar_relatorio_terminal(db_path: Path = DB_PATH) -> None:
    """Imprime no terminal uma visão consolidada das publicações registradas."""
    inicializar_banco(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status_geral, COUNT(*) as qtd FROM produtos GROUP BY status_geral;")
        resumo_geral = {r["status_geral"]: r["qtd"] for r in cursor.fetchall()}

        cursor.execute("SELECT canal, status, COUNT(*) as qtd FROM canais_status GROUP BY canal, status;")
        resumo_canais = {}
        for r in cursor.fetchall():
            resumo_canais.setdefault(r["canal"], {})[r["status"]] = r["qtd"]

        cursor.execute("SELECT * FROM produtos ORDER BY atualizado_em DESC LIMIT 20;")
        recentes = cursor.fetchall()

    print("\n=======================================================")
    print("📊 RELATÓRIO DE CONTROLE DE PUBLICAÇÕES (SQLite)")
    print("=======================================================")
    print(f"Total Concluídos (5/5 canais): {resumo_geral.get('CONCLUIDO', 0)}")
    print(f"Total Parciais:                {resumo_geral.get('PARCIAL', 0)}")
    print(f"Total com Falha/Pendentes:     {resumo_geral.get('FALHA', 0) + resumo_geral.get('PENDENTE', 0)}")
    print("-------------------------------------------------------")
    print("Status detalhado por Canal:")
    for canal in CANAIS_OBRIGATORIOS:
        stats = resumo_canais.get(canal, {})
        suc = stats.get("SUCESSO", 0)
        fal = stats.get("FALHA", 0)
        print(f"  • {canal.ljust(18)}: {suc} sucesso(s) | {fal} falha(s)")
    print("=======================================================\n")


def obter_resumo_estatisticas(db_path: Path = DB_PATH) -> dict:
    """Retorna métricas consolidadas de produtos e status por canal para o dashboard."""
    inicializar_banco(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM produtos;")
        total_produtos = cursor.fetchone()["total"]

        cursor.execute("SELECT status_geral, COUNT(*) as qtd FROM produtos GROUP BY status_geral;")
        resumo_geral = {r["status_geral"]: r["qtd"] for r in cursor.fetchall()}

        cursor.execute("SELECT canal, status, COUNT(*) as qtd FROM canais_status GROUP BY canal, status;")
        resumo_canais = {}
        for canal in CANAIS_OBRIGATORIOS:
            resumo_canais[canal] = {"SUCESSO": 0, "FALHA": 0, "PENDENTE": 0}
        for r in cursor.fetchall():
            c = r["canal"]
            if c in resumo_canais:
                resumo_canais[c][r["status"]] = r["qtd"]

    return {
        "total_produtos": total_produtos,
        "concluidos": resumo_geral.get("CONCLUIDO", 0),
        "parciais": resumo_geral.get("PARCIAL", 0),
        "falhas": resumo_geral.get("FALHA", 0),
        "pendentes": resumo_geral.get("PENDENTE", 0),
        "canais": resumo_canais,
    }


def listar_produtos_paginado(
    pagina: int = 1,
    limite: int = 20,
    status_filtro: str | None = None,
    busca: str | None = None,
    db_path: Path = DB_PATH,
) -> dict:
    """Retorna uma lista paginada de produtos com seus status de canal acoplados."""
    inicializar_banco(db_path)
    if pagina < 1:
        pagina = 1
    offset = (pagina - 1) * limite

    query_where = []
    params = []

    if status_filtro and status_filtro != "TODOS":
        query_where.append("status_geral = ?")
        params.append(status_filtro)

    if busca:
        query_where.append("(item_id LIKE ? OR item_name LIKE ?)")
        params.extend([f"%{busca}%", f"%{busca}%"])

    where_clause = f"WHERE {' AND '.join(query_where)}" if query_where else ""

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) as total FROM produtos {where_clause};", params)
        total = cursor.fetchone()["total"]

        cursor.execute(
            f"SELECT * FROM produtos {where_clause} ORDER BY criado_em DESC LIMIT ? OFFSET ?;",
            params + [limite, offset],
        )
        itens = []
        for row in cursor.fetchall():
            prod = dict(row)
            prod["canais_status"] = obter_status_canais(prod["item_id"], db_path)
            itens.append(prod)

    total_paginas = (total + limite - 1) // limite if limite > 0 else 1

    return {
        "total": total,
        "pagina": pagina,
        "limite": limite,
        "total_paginas": total_paginas,
        "itens": itens,
    }


def inserir_lote_produtos(produtos: list[dict], db_path: Path = DB_PATH) -> dict:
    """Insere produtos no banco, ignorando rigorosamente qualquer Item ID já cadastrado ou repetido no lote."""
    import re
    inicializar_banco(db_path)
    total_lidos = len(produtos)
    novos_inseridos = 0
    duplicados_ignorados = 0
    itens_ignorados = []
    erros = []

    # Pré-carrega todos os Item IDs já existentes no banco para checagem rápida em memória
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT item_id FROM produtos;")
        ids_vistos = {str(r["item_id"]).strip() for r in cursor.fetchall()}

    for idx, prod in enumerate(produtos):
        try:
            # Normalização de chaves insensível a maiúsculas e caracteres especiais
            prod_norm = {str(k).strip().lower().replace("_", "").replace(" ", ""): v for k, v in prod.items()}
            
            def get_val(*candidatos):
                for c in candidatos:
                    cn = c.lower().replace("_", "").replace(" ", "")
                    if cn in prod_norm and prod_norm[cn] is not None:
                        return str(prod_norm[cn]).strip()
                return ""

            item_id = get_val("item_id", "item id", "itemid", "id")
            item_name = get_val("item_name", "item name", "nome", "produto", "title")
            offer_link = get_val("offer_link", "offer link", "link oferta", "offerlink")
            product_link = get_val("product_link", "product link", "link produto", "productlink")
            price = get_val("price", "preco", "preço", "valor")
            image_url = get_val("image_url", "image url", "image", "imagem", "foto", "product_image", "productimage", "photourl")

            # Fallback para extrair item_id da URL caso o cabeçalho não traga coluna explícita
            if not item_id and product_link:
                m = re.search(r'/(\d{8,})(?:\?|$)', product_link)
                if m:
                    item_id = m.group(1)
            if not item_id and offer_link:
                item_id = offer_link.strip("/").split("/")[-1]

            item_id = str(item_id).strip()

            if not item_id or not item_name or not offer_link:
                erros.append(f"Linha {idx + 1}: dados mínimos ausentes (Item Id: '{item_id}', Item Name: '{item_name}', Offer Link: '{offer_link}')")
                continue

            # Regra obrigatória: ignora inclusão se o Item ID já existe no banco ou já foi lido neste lote
            if item_id in ids_vistos:
                duplicados_ignorados += 1
                itens_ignorados.append(item_id)
                continue

            dados_prod = {
                "item_id": item_id,
                "item_name": item_name,
                "offer_link": offer_link,
                "product_link": product_link,
                "price": price,
                "image_url": image_url or None,
            }
            inserido = registrar_produto(dados_prod, db_path, ignorar_se_existir=True)
            if inserido:
                ids_vistos.add(item_id)
                novos_inseridos += 1
            else:
                duplicados_ignorados += 1
                itens_ignorados.append(item_id)
        except Exception as e:
            erros.append(f"Linha {idx + 1}: erro ao processar: {str(e)}")

    return {
        "total_lidos": total_lidos,
        "novos_inseridos": novos_inseridos,
        "duplicados_ignorados": duplicados_ignorados,
        "itens_ignorados": itens_ignorados,
        "erros": erros,
    }


def obter_historico_logs_produto(item_id: str, db_path: Path = DB_PATH) -> list[dict]:
    """Retorna os logs históricos de auditoria para um produto específico."""
    inicializar_banco(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM historico_logs WHERE item_id = ? ORDER BY data_envio DESC;",
            (str(item_id),),
        )
        return [dict(r) for r in cursor.fetchall()]


def excluir_produto(item_id: str, db_path: Path = DB_PATH) -> bool:
    """Exclui um produto, seus status e logs do banco."""
    inicializar_banco(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM historico_logs WHERE item_id = ?;", (str(item_id),))
        cursor.execute("DELETE FROM canais_status WHERE item_id = ?;", (str(item_id),))
        cursor.execute("DELETE FROM produtos WHERE item_id = ?;", (str(item_id),))
        conn.commit()
        return cursor.rowcount > 0


def excluir_lote_produtos(item_ids: list[str], db_path: Path = DB_PATH) -> int:
    """Exclui múltiplos produtos e seus dados associados em lote."""
    if not item_ids:
        return 0
    inicializar_banco(db_path)
    ids_str = [str(i) for i in item_ids]
    placeholders = ",".join("?" for _ in ids_str)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM historico_logs WHERE item_id IN ({placeholders});", ids_str)
        cursor.execute(f"DELETE FROM canais_status WHERE item_id IN ({placeholders});", ids_str)
        cursor.execute(f"DELETE FROM produtos WHERE item_id IN ({placeholders});", ids_str)
        total_removidos = cursor.rowcount
        conn.commit()
        return total_removidos


def localizar_artes_produto(item_id: str, pasta_artes_registrada: str | None = None) -> dict[str, Path]:
    """Localiza as artes geradas no disco (em db/img/) para evitar renderizações desnecessárias."""
    artes = {}
    item_id_str = str(item_id).strip()
    pastas_candidatas = []

    if pasta_artes_registrada:
        p_cand = Path(pasta_artes_registrada)
        if not p_cand.is_absolute():
            p_cand = ROOT / p_cand
        pastas_candidatas.append(p_cand)

    base_db_img = ROOT / "db" / "img"
    if base_db_img.exists():
        for d in sorted(base_db_img.glob(f"*/{item_id_str}"), reverse=True):
            if d.is_dir() and d not in pastas_candidatas:
                pastas_candidatas.append(d)

    legado_dir = ROOT / "instagran" / "img"
    if legado_dir.exists() and legado_dir not in pastas_candidatas:
        pastas_candidatas.append(legado_dir)

    for pasta in pastas_candidatas:
        if not pasta.exists():
            continue

        stories = pasta / f"{item_id_str}_stories.png"
        post = pasta / f"{item_id_str}_post.png"
        reeals = pasta / f"{item_id_str}_reeals.png"
        reels_alias = pasta / f"{item_id_str}_reels.png"

        if stories.exists():
            artes["stories"] = stories
        if post.exists():
            artes["post"] = post
        if reeals.exists():
            artes["reeals"] = reeals
            artes["reels"] = reeals
        elif reels_alias.exists():
            artes["reeals"] = reels_alias
            artes["reels"] = reels_alias

        if "stories" in artes and "post" in artes and "reels" in artes:
            artes["pasta"] = pasta
            artes["codigo"] = item_id_str
            return artes

    return artes



