import { Injectable, inject, signal } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import {
  Produto,
  PaginacaoProdutos,
  ResumoEstatisticas,
  DetalheProdutoResposta,
  UploadResultado,
  IntegracoesResposta,
  ShopeeOfertaItem,
  ShopeeOfertasResposta,
  ShopeeConversoesResposta,
  ListaItem,
  EnvioStatusResposta,
} from '../models/produto.model';

@Injectable({
  providedIn: 'root',
})
export class AfiliadosService {
  private http = inject(HttpClient);
  private baseUrl = 'http://localhost:8000/api';

  // Signals para reatividade global no Angular 22
  estatisticas = signal<ResumoEstatisticas | null>(null);
  carregando = signal<boolean>(false);
  reenviandoLote = signal<boolean>(false);

  /**
   * Obtém as estatísticas consolidadas para os cards do Dashboard.
   */
  carregarEstatisticas(): Observable<ResumoEstatisticas> {
    return this.http.get<ResumoEstatisticas>(`${this.baseUrl}/estatisticas`).pipe(
      tap((stats) => this.estatisticas.set(stats))
    );
  }

  /**
   * Obtém a lista de listas cadastradas com quantidade de produtos associados.
   */
  getListas(): Observable<ListaItem[]> {
    return this.http.get<ListaItem[]>(`${this.baseUrl}/listas`);
  }

  /**
   * Cria ou garante a existência de uma lista temática.
   */
  criarLista(nome: string): Observable<{ sucesso: boolean; nome: string }> {
    return this.http.post<{ sucesso: boolean; nome: string }>(`${this.baseUrl}/listas`, { nome });
  }

  /**
   * Exclui uma lista temática.
   */
  excluirLista(nome: string, desvincular: boolean = true): Observable<{ sucesso: boolean }> {
    return this.http.delete<{ sucesso: boolean }>(`${this.baseUrl}/listas/${encodeURIComponent(nome)}`, {
      params: new HttpParams().set('desvincular', desvincular.toString()),
    });
  }

  /**
   * Obtém a lista paginada de produtos com busca, filtro de status e filtro de lista.
   */
  getProdutos(
    pagina: number = 1,
    limite: number = 10,
    status?: string,
    busca?: string,
    lista?: string
  ): Observable<PaginacaoProdutos> {
    let params = new HttpParams()
      .set('pagina', pagina.toString())
      .set('limite', limite.toString());

    if (status && status !== 'TODOS') {
      params = params.set('status', status);
    }
    if (busca && busca.trim()) {
      params = params.set('busca', busca.trim());
    }
    if (lista && lista !== 'TODAS') {
      params = params.set('lista', lista);
    }

    return this.http.get<PaginacaoProdutos>(`${this.baseUrl}/produtos`, { params });
  }

  /**
   * Obtém os detalhes e logs de auditoria de um produto específico.
   */
  getDetalheProduto(itemId: string): Observable<DetalheProdutoResposta> {
    return this.http.get<DetalheProdutoResposta>(`${this.baseUrl}/produtos/${itemId}`);
  }

  /**
   * Faz upload de arquivo CSV para carga de produtos no banco de dados.
   */
  uploadCSV(nomeArquivo: string, conteudo: string): Observable<UploadResultado> {
    return this.http.post<UploadResultado>(`${this.baseUrl}/produtos/upload-csv`, {
      nome_arquivo: nomeArquivo,
      conteudo,
    }).pipe(
      tap(() => this.carregarEstatisticas().subscribe())
    );
  }

  /**
   * Consulta o estado em tempo real do envio/reenvio em segundo plano.
   */
  getEnvioStatus(): Observable<EnvioStatusResposta> {
    return this.http.get<EnvioStatusResposta>(`${this.baseUrl}/produtos/envio-status`);
  }

  /**
   * Cadastra um produto extraindo automaticamente seus metadados a partir de um link de afiliado/produto.
   */
  adicionarProdutoPorLink(
    url: string,
    lista?: string
  ): Observable<{ sucesso: boolean; mensagem: string; produto: Produto }> {
    const payload: { url: string; lista?: string } = { url: url.trim() };
    if (lista && lista.trim() && lista !== 'TODAS' && lista !== 'SEM_LISTA') {
      payload.lista = lista.trim();
    }
    return this.http
      .post<{ sucesso: boolean; mensagem: string; produto: Produto }>(
        `${this.baseUrl}/produtos/adicionar-link`,
        payload
      )
      .pipe(tap(() => this.carregarEstatisticas().subscribe()));
  }

  /**
   * Dispara o reenvio cirúrgico dos canais pendentes de um produto.
   */
  reenviarProduto(itemId: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/produtos/${itemId}/reenviar`, { dry_run: false });
  }

  /**
   * Dispara o envio dos produtos selecionados na tabela.
   */
  enviarSelecionados(itemIds: string[]): Observable<any> {
    return this.http.post(`${this.baseUrl}/produtos/enviar-selecionados`, {
      item_ids: itemIds,
      dry_run: false,
    }).pipe(
      tap(() => setTimeout(() => this.carregarEstatisticas().subscribe(), 2000))
    );
  }

  /**
   * Exclui múltiplos produtos selecionados no banco de dados.
   */
  excluirSelecionados(itemIds: string[]): Observable<any> {
    return this.http.post(`${this.baseUrl}/produtos/excluir-selecionados`, {
      item_ids: itemIds,
    }).pipe(
      tap(() => this.carregarEstatisticas().subscribe())
    );
  }

  /**
   * Dispara o reenvio de todos os produtos pendentes/falhos em lote.
   */
  reenviarTodosFalhas(): Observable<any> {
    this.reenviandoLote.set(true);
    return this.http.post(`${this.baseUrl}/produtos/reenviar-falhas`, { dry_run: false }).pipe(
      tap({
        next: () => setTimeout(() => this.reenviandoLote.set(false), 3000),
        error: () => this.reenviandoLote.set(false),
      })
    );
  }

  /**
   * Exclui um produto do banco de dados.
   */
  excluirProduto(itemId: string): Observable<any> {
    return this.http.delete(`${this.baseUrl}/produtos/${itemId}`).pipe(
      tap(() => this.carregarEstatisticas().subscribe())
    );
  }

  /**
   * Consulta o status das integrações e credenciais.
   */
  getIntegracoesStatus(): Observable<IntegracoesResposta> {
    return this.http.get<IntegracoesResposta>(`${this.baseUrl}/integracoes/status`);
  }

  /**
   * Consulta o catálogo de ofertas da Shopee Affiliate Open API em tempo real.
   */
  buscarOfertasShopee(
    keyword?: string,
    sortType: number = 2,
    page: number = 1,
    limit: number = 20,
    itemId?: number
  ): Observable<ShopeeOfertasResposta> {
    let params = new HttpParams()
      .set('sort_type', sortType.toString())
      .set('page', page.toString())
      .set('limit', limit.toString());

    if (keyword && keyword.trim()) {
      params = params.set('keyword', keyword.trim());
    }
    if (itemId) {
      params = params.set('item_id', itemId.toString());
    }

    return this.http.get<ShopeeOfertasResposta>(`${this.baseUrl}/shopee/ofertas`, { params });
  }

  /**
   * Importa ofertas selecionadas da Shopee diretamente para o banco de dados, opcionalmente associando a uma lista.
   */
  importarOfertasShopee(
    itens: ShopeeOfertaItem[],
    lista?: string
  ): Observable<{ sucesso: boolean; total_importados: number; mensagem: string; lista?: string }> {
    const payload: { itens: ShopeeOfertaItem[]; lista?: string } = { itens };
    if (lista && lista.trim()) {
      payload.lista = lista.trim();
    }
    return this.http.post<{ sucesso: boolean; total_importados: number; mensagem: string; lista?: string }>(
      `${this.baseUrl}/shopee/importar-ofertas`,
      payload
    ).pipe(
      tap(() => this.carregarEstatisticas().subscribe())
    );
  }

  /**
   * Retorna histórico consolidado e pedidos faturados da Shopee.
   */
  getShopeeConversoes(limite: number = 50): Observable<ShopeeConversoesResposta> {
    const params = new HttpParams().set('limite', limite.toString());
    return this.http.get<ShopeeConversoesResposta>(`${this.baseUrl}/shopee/conversoes`, { params });
  }

  /**
   * Dispara a sincronização e reconciliação contábil de conversões com a Shopee.
   */
  sincronizarShopeeConversoes(limit: number = 50): Observable<{ sucesso: boolean; total_sincronizados: number; mensagem: string }> {
    const params = new HttpParams().set('limit', limit.toString());
    return this.http.post<{ sucesso: boolean; total_sincronizados: number; mensagem: string }>(
      `${this.baseUrl}/shopee/sincronizar-conversoes`,
      {},
      { params }
    );
  }
}
