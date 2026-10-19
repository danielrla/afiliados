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
   * Obtém a lista paginada de produtos com busca e filtro de status.
   */
  getProdutos(
    pagina: number = 1,
    limite: number = 10,
    status?: string,
    busca?: string
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
   * Dispara o reenvio cirúrgico dos canais pendentes de um produto.
   */
  reenviarProduto(itemId: string, dryRun: boolean = false): Observable<any> {
    return this.http.post(`${this.baseUrl}/produtos/${itemId}/reenviar`, { dry_run: dryRun });
  }

  /**
   * Dispara o envio dos produtos selecionados na tabela.
   */
  enviarSelecionados(itemIds: string[], dryRun: boolean = false): Observable<any> {
    return this.http.post(`${this.baseUrl}/produtos/enviar-selecionados`, {
      item_ids: itemIds,
      dry_run: dryRun,
    }).pipe(
      tap(() => setTimeout(() => this.carregarEstatisticas().subscribe(), 3000))
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
  reenviarTodosFalhas(dryRun: boolean = false): Observable<any> {
    this.reenviandoLote.set(true);
    return this.http.post(`${this.baseUrl}/produtos/reenviar-falhas`, { dry_run: dryRun }).pipe(
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
}
