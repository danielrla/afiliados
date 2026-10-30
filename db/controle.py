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
    "facebook_reels",
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

        # Tabela de reconciliação de conversões da Shopee
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS shopee_conversoes (
            conversion_id TEXT PRIMARY KEY,
            order_id TEXT,
            item_id TEXT,
            item_name TEXT,
            item_price REAL,
            item_commission REAL,
            order_status TEXT,
            channel_type TEXT,
            purchase_time TEXT,
            criado_em TEXT
        );
        """)

        # Tabela de listas temáticas de produtos
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS listas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            criado_em TEXT
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
        if "commission_rate" not in cols_prod:
            cursor.execute("ALTER TABLE produtos ADD COLUMN commission_rate TEXT;")
        if "sales" not in cols_prod:
            cursor.execute("ALTER TABLE produtos ADD COLUMN sales INTEGER DEFAULT 0;")
        if "rating_star" not in cols_prod:
            cursor.execute("ALTER TABLE produtos ADD COLUMN rating_star REAL DEFAULT 0.0;")
        if "lista" not in cols_prod:
            cursor.execute("ALTER TABLE produtos ADD COLUMN lista TEXT;")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_produtos_lista ON produtos(lista);")

        cursor.execute("PRAGMA table_info(canais_status);")
        cols_canais = [r["name"] for r in cursor.fetchall()]
        if "link_rastreado" not in cols_canais:
            cursor.execute("ALTER TABLE canais_status ADD COLUMN link_rastreado TEXT;")

        # Reconcilia produtos antigos marcados como CONCLUIDO antes da exigência dos 6 canais obrigatórios
        cursor.execute("""
        UPDATE produtos
        SET status_geral = 'PARCIAL'
        WHERE status_geral = 'CONCLUIDO'
          AND (
              SELECT COUNT(*) FROM canais_status cs
              WHERE cs.item_id = produtos.item_id AND cs.status = 'SUCESSO'
          ) < ?;
        """, (len(CANAIS_OBRIGATORIOS),))

        conn.commit()


def garantir_lista(nome: str, db_path: Path = DB_PATH) -> str:
    """Garante que a lista temática exista na tabela listas e retorna seu nome sanitizado."""
    inicializar_banco(db_path)
    nome_limpo = str(nome or "").strip()
    if not nome_limpo:
        raise ValueError("O nome da lista não pode ser vazio.")

    agora = datetime.datetime.now().isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO listas (nome, criado_em)
        VALUES (?, ?)
        ON CONFLICT(nome) DO NOTHING;
        """, (nome_limpo, agora))
        conn.commit()
    return nome_limpo


def listar_todas_listas(db_path: Path = DB_PATH) -> list[dict]:
    """Retorna todas as listas cadastradas acompanhadas da quantidade de produtos associados."""
    inicializar_banco(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT 
            l.id,
            l.nome,
            l.criado_em,
            COUNT(p.item_id) as total_produtos
        FROM listas l
        LEFT JOIN produtos p ON p.lista = l.nome
        GROUP BY l.id, l.nome, l.criado_em
        ORDER BY l.nome COLLATE NOCASE ASC;
        """)
        return [dict(r) for r in cursor.fetchall()]


def excluir_lista(nome: str, desvincular_produtos: bool = True, db_path: Path = DB_PATH) -> bool:
    """Exclui uma lista cadastrada e opcionalmente desvincula os produtos associados a ela."""
    inicializar_banco(db_path)
    nome_limpo = str(nome or "").strip()
    if not nome_limpo:
        return False

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if desvincular_produtos:
            cursor.execute("UPDATE produtos SET lista = NULL WHERE lista = ?;", (nome_limpo,))
        cursor.execute("DELETE FROM listas WHERE nome = ?;", (nome_limpo,))
        removidos = cursor.rowcount
        conn.commit()
    return removidos > 0


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
    
    lista = str(produto.get("lista", "")).strip() if produto.get("lista") else None
    if lista:
        garantir_lista(lista, db_path=db_path)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if ignorar_se_existir:
            cursor.execute("SELECT 1 FROM produtos WHERE item_id = ? LIMIT 1;", (item_id,))
            if cursor.fetchone():
                return False

        cursor.execute("""
        INSERT INTO produtos (item_id, item_name, offer_link, product_link, price, image_url, codigo_artes, pasta_artes, lista, criado_em, atualizado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            item_name=excluded.item_name,
            offer_link=excluded.offer_link,
            product_link=excluded.product_link,
            price=excluded.price,
            image_url=COALESCE(excluded.image_url, produtos.image_url),
            codigo_artes=COALESCE(excluded.codigo_artes, produtos.codigo_artes),
            pasta_artes=COALESCE(excluded.pasta_artes, produtos.pasta_artes),
            lista=COALESCE(excluded.lista, produtos.lista),
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
            lista,
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


def obter_links_rastreados_produto(item_id: str, db_path: Path = DB_PATH) -> dict[str, str]:
    """Retorna um dicionário com os links rastreados já gerados e salvos por canal para evitar chamadas repetidas à Shopee."""
    inicializar_banco(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT canal, link_rastreado FROM canais_status WHERE item_id = ? AND link_rastreado IS NOT NULL AND link_rastreado != ''",
            (str(item_id),),
        )
        return {r["canal"]: r["link_rastreado"] for r in cursor.fetchall()}


def marcar_canal_enviando(item_id: str, canal: str, db_path: Path = DB_PATH) -> None:
    """Marca transitoriamente um canal e o produto como ENVIANDO para acompanhamento em tempo real na UI."""
    inicializar_banco(db_path)
    agora = datetime.datetime.now().isoformat()
    item_id_str = str(item_id)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO canais_status (item_id, canal, status, tentativas, atualizado_em)
        VALUES (?, ?, 'ENVIANDO', 0, ?)
        ON CONFLICT(item_id, canal) DO UPDATE SET
            status = 'ENVIANDO',
            atualizado_em = excluded.atualizado_em;
        """, (item_id_str, canal, agora))
        cursor.execute("""
        UPDATE produtos SET status_geral = 'ENVIANDO', atualizado_em = ? WHERE item_id = ?;
        """, (agora, item_id_str))
        conn.commit()


def registrar_resultado_canal(
    item_id: str,
    canal: str,
    status: str,
    id_externo: str | None = None,
    mensagem_erro: str | None = None,
    caminho_imagem: str | None = None,
    link_rastreado: str | None = None,
    db_path: Path = DB_PATH,
) -> None:
    """Atualiza o resultado de envio de um canal, grava o caminho da mídia no log e recalcula o status geral."""
    inicializar_banco(db_path)
    agora = datetime.datetime.now().isoformat()
    item_id_str = str(item_id)
    caminho_img_str = str(caminho_imagem) if caminho_imagem else None
    link_rastreado_str = str(link_rastreado) if link_rastreado else None

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Atualiza ou insere o status do canal incrementando o número de tentativas
        cursor.execute("""
        INSERT INTO canais_status (item_id, canal, status, id_externo, mensagem_erro, link_rastreado, tentativas, atualizado_em)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(item_id, canal) DO UPDATE SET
            status = excluded.status,
            id_externo = COALESCE(excluded.id_externo, canais_status.id_externo),
            mensagem_erro = excluded.mensagem_erro,
            link_rastreado = COALESCE(excluded.link_rastreado, canais_status.link_rastreado),
            tentativas = canais_status.tentativas + 1,
            atualizado_em = excluded.atualizado_em;
        """, (item_id_str, canal, status, id_externo, mensagem_erro, link_rastreado_str, agora))

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
    print(f"Total Concluídos (6/6 canais): {resumo_geral.get('CONCLUIDO', 0)}")
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
    lista_filtro: str | None = None,
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

    if lista_filtro and lista_filtro != "TODAS":
        if lista_filtro == "SEM_LISTA":
            query_where.append("(lista IS NULL OR lista = '')")
        else:
            query_where.append("lista = ?")
            params.append(lista_filtro)

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
    """Localiza as artes geradas no disco (em db/img/) validando se são mais recentes que instagran/templates/."""
    artes = {}
    item_id_str = str(item_id).strip()
    pastas_candidatas = []

    templates_dir = ROOT / "instagran" / "templates"
    templates_mtime = 0.0
    if templates_dir.exists():
        for tpl_file in templates_dir.iterdir():
            if tpl_file.is_file() and tpl_file.suffix.lower() in (".html", ".png", ".jpg", ".jpeg"):
                templates_mtime = max(templates_mtime, tpl_file.stat().st_mtime)

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
        reeals_mp4 = pasta / f"{item_id_str}_reeals.mp4"

        cand_artes = {}
        if stories.exists() and stories.stat().st_mtime >= templates_mtime:
            cand_artes["stories"] = stories
        if post.exists() and post.stat().st_mtime >= templates_mtime:
            cand_artes["post"] = post
        if reeals.exists() and reeals.stat().st_mtime >= templates_mtime:
            cand_artes["reeals"] = reeals
            cand_artes["reels"] = reeals
        elif reels_alias.exists() and reels_alias.stat().st_mtime >= templates_mtime:
            cand_artes["reeals"] = reels_alias
            cand_artes["reels"] = reels_alias

        mp4_valido = (
            reeals_mp4.exists()
            and reeals_mp4.stat().st_mtime >= templates_mtime
            and reeals_mp4.stat().st_size >= 50000
        )

        if "stories" in cand_artes and "post" in cand_artes and "reels" in cand_artes and mp4_valido:
            cand_artes["reels_mp4"] = reeals_mp4
            cand_artes["reeals_mp4"] = reeals_mp4
            cand_artes["pasta"] = pasta
            cand_artes["codigo"] = item_id_str
            return cand_artes

    return artes


def salvar_conversoes_shopee(conversoes: list[dict], db_path: Path = DB_PATH) -> int:
    """Insere ou atualiza registros de conversão da Shopee para reconciliação contábil."""
    if not conversoes:
        return 0
    inicializar_banco(db_path)
    agora = datetime.datetime.now().isoformat()
    total_salvos = 0
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        for c in conversoes:
            conv_id = str(c.get("conversion_id") or "").strip()
            if not conv_id:
                continue
            cursor.execute("""
            INSERT INTO shopee_conversoes (
                conversion_id, order_id, item_id, item_name, item_price,
                item_commission, order_status, channel_type, purchase_time, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(conversion_id) DO UPDATE SET
                order_status = excluded.order_status,
                item_commission = excluded.item_commission,
                item_price = excluded.item_price;
            """, (
                conv_id,
                str(c.get("order_id") or ""),
                str(c.get("item_id") or ""),
                str(c.get("item_name") or ""),
                float(c.get("item_price") or 0.0),
                float(c.get("item_commission") or 0.0),
                str(c.get("order_status") or ""),
                c.get("channel_type"),
                str(c.get("purchase_time") or ""),
                agora,
            ))
            total_salvos += 1
        conn.commit()
    return total_salvos


def obter_resumo_conversoes(db_path: Path = DB_PATH) -> dict:
    """Retorna métricas agregadas de comissões e pedidos faturados."""
    inicializar_banco(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total, COALESCE(SUM(item_commission), 0) as total_comissao, COALESCE(SUM(item_price), 0) as total_vendas FROM shopee_conversoes;")
        geral = dict(cursor.fetchone())

        cursor.execute("SELECT order_status, COUNT(*) as qtd FROM shopee_conversoes GROUP BY order_status;")
        por_status = {r["order_status"]: r["qtd"] for r in cursor.fetchall()}

        cursor.execute("SELECT channel_type, COUNT(*) as qtd, COALESCE(SUM(item_commission), 0) as comissao FROM shopee_conversoes WHERE channel_type IS NOT NULL GROUP BY channel_type;")
        por_canal = [dict(r) for r in cursor.fetchall()]

        return {
            "total_pedidos": geral["total"],
            "total_comissao_reais": round(float(geral["total_comissao"]), 2),
            "total_vendas_reais": round(float(geral["total_vendas"]), 2),
            "pedidos_por_status": por_status,
            "comissao_por_canal": por_canal,
        }


def listar_conversoes(limite: int = 50, db_path: Path = DB_PATH) -> list[dict]:
    """Lista as conversões registradas no banco por ordem decrescente."""
    inicializar_banco(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT conversion_id, order_id, item_id, item_name, item_price, item_commission, order_status, channel_type, purchase_time, criado_em
        FROM shopee_conversoes
        ORDER BY rowid DESC
        LIMIT ?;
        """, (limite,))
        return [dict(r) for r in cursor.fetchall()]




