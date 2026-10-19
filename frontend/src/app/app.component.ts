import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AfiliadosService } from './services/afiliados.service';
import {
  Produto,
  PaginacaoProdutos,
  ResumoEstatisticas,
  DetalheProdutoResposta,
  IntegracoesResposta,
} from './models/produto.model';

type AbaAtiva = 'produtos' | 'upload' | 'dashboard' | 'integracoes';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
})
export class AppComponent implements OnInit {
  protected afiliadosService = inject(AfiliadosService);

  // Estados com Signals
  abaAtiva = signal<AbaAtiva>('produtos');
  produtosData = signal<PaginacaoProdutos | null>(null);
  estatisticas = signal<ResumoEstatisticas | null>(null);
  integracoes = signal<IntegracoesResposta | null>(null);
  produtoSelecionado = signal<DetalheProdutoResposta | null>(null);

  // Filtros e Paginação
  buscaTermo = '';
  filtroStatus = 'TODOS';
  paginaAtual = 1;
  limitePorPagina = 10;
  carregandoLista = false;
  mensagemAlerta = signal<{ tipo: 'sucesso' | 'erro' | 'info'; texto: string } | null>(null);

  // Upload de CSV
  arquivoUpload: File | null = null;
  previewUpload: any[] = [];
  uploading = false;
  nomeArquivoUpload = '';

  // Modo Dry-run
  modoDryRun = false;

  // Seleção múltipla de produtos
  itensSelecionados = signal<Set<string>>(new Set());
  enviandoSelecionados = signal<boolean>(false);
  excluindoSelecionados = signal<boolean>(false);

  readonly canais = [
    { id: 'whatsapp', nome: 'WhatsApp', icone: '💬' },
    { id: 'facebook', nome: 'Facebook', icone: '📘' },
    { id: 'instagram_stories', nome: 'Stories', icone: '📱' },
    { id: 'instagram_post', nome: 'Post Feed', icone: '📸' },
    { id: 'instagram_reels', nome: 'Reels', icone: '🎬' },
  ];

  ngOnInit(): void {
    this.carregarDados();
    this.carregarIntegracoes();
  }

  carregarDados(): void {
    this.carregarListaProdutos();
    this.afiliadosService.carregarEstatisticas().subscribe({
      next: (stats) => this.estatisticas.set(stats),
    });
  }

  carregarListaProdutos(): void {
    this.carregandoLista = true;
    this.afiliadosService
      .getProdutos(this.paginaAtual, this.limitePorPagina, this.filtroStatus, this.buscaTermo)
      .subscribe({
        next: (data) => {
          this.produtosData.set(data);
          this.carregandoLista = false;
        },
        error: (err) => {
          this.mostrarAlerta('erro', 'Falha ao conectar com o backend. Verifique se o servidor está ativo.');
          this.carregandoLista = false;
        },
      });
  }

  carregarIntegracoes(): void {
    this.afiliadosService.getIntegracoesStatus().subscribe({
      next: (res) => this.integracoes.set(res),
      error: () => {},
    });
  }

  setAba(aba: AbaAtiva): void {
    this.abaAtiva.set(aba);
  }

  onBuscaSubmit(): void {
    this.paginaAtual = 1;
    this.carregarListaProdutos();
  }

  onFiltroStatusChange(novoStatus: string): void {
    this.filtroStatus = novoStatus;
    this.paginaAtual = 1;
    this.carregarListaProdutos();
  }

  mudarPagina(novaPagina: number): void {
    const total = this.produtosData()?.total_paginas || 1;
    if (novaPagina >= 1 && novaPagina <= total && novaPagina !== this.paginaAtual) {
      this.paginaAtual = novaPagina;
      this.carregarListaProdutos();
    }
  }

  mudarLimite(novoLimite: number): void {
    this.limitePorPagina = novoLimite;
    this.paginaAtual = 1;
    this.carregarListaProdutos();
  }

  obterArrayPaginas(): number[] {
    const total = this.produtosData()?.total_paginas || 1;
    const maxVisiveis = 5;
    let start = Math.max(1, this.paginaAtual - 2);
    let end = Math.min(total, start + maxVisiveis - 1);
    if (end - start < maxVisiveis - 1) {
      start = Math.max(1, end - maxVisiveis + 1);
    }
    const paginas: number[] = [];
    for (let i = start; i <= end; i++) {
      paginas.push(i);
    }
    return paginas;
  }

  abrirDetalhes(itemId: string): void {
    this.afiliadosService.getDetalheProduto(itemId).subscribe({
      next: (res) => this.produtoSelecionado.set(res),
      error: () => this.mostrarAlerta('erro', 'Não foi possível carregar os detalhes do produto.'),
    });
  }

  fecharModal(): void {
    this.produtoSelecionado.set(null);
  }

  reenviarProduto(itemId: string): void {
    this.mostrarAlerta('info', `Iniciando reenvio de pendências para o item ${itemId}...`);
    this.afiliadosService.reenviarProduto(itemId, this.modoDryRun).subscribe({
      next: (res) => {
        this.mostrarAlerta('sucesso', res.mensagem || 'Reenvio agendado em segundo plano.');
        setTimeout(() => this.carregarDados(), 2500);
      },
      error: (err) => this.mostrarAlerta('erro', 'Falha ao solicitar reenvio do item.'),
    });
  }

  reenviarTodasFalhas(): void {
    this.mostrarAlerta('info', 'Disparando rotina de reprocessamento em lote...');
    this.afiliadosService.reenviarTodosFalhas(this.modoDryRun).subscribe({
      next: (res) => {
        this.mostrarAlerta('sucesso', res.mensagem || 'Reenvio em lote em andamento.');
        setTimeout(() => this.carregarDados(), 3000);
      },
      error: (err) => this.mostrarAlerta('erro', 'Falha ao iniciar reenvio em lote.'),
    });
  }

  excluirItem(itemId: string, event: Event): void {
    event.stopPropagation();
    if (confirm(`Confirma a exclusão do produto ID ${itemId} e de todo o seu histórico?`)) {
      this.afiliadosService.excluirProduto(itemId).subscribe({
        next: () => {
          this.mostrarAlerta('sucesso', `Produto ${itemId} removido com sucesso.`);
          this.carregarDados();
        },
        error: () => this.mostrarAlerta('erro', 'Erro ao excluir produto.'),
      });
    }
  }

  isItemSelecionado(itemId: string): boolean {
    return this.itensSelecionados().has(itemId);
  }

  toggleSelectProduto(itemId: string, event: Event): void {
    const input = event.target as HTMLInputElement;
    const novoSet = new Set(this.itensSelecionados());
    if (input.checked) {
      novoSet.add(itemId);
    } else {
      novoSet.delete(itemId);
    }
    this.itensSelecionados.set(novoSet);
  }

  toggleSelectTodos(event: Event): void {
    const input = event.target as HTMLInputElement;
    const novoSet = new Set(this.itensSelecionados());
    const itens = this.produtosData()?.itens || [];
    itens.forEach((p) => {
      if (input.checked) {
        novoSet.add(p.item_id);
      } else {
        novoSet.delete(p.item_id);
      }
    });
    this.itensSelecionados.set(novoSet);
  }

  todosDestaPaginaSelecionados(): boolean {
    const itens = this.produtosData()?.itens || [];
    if (!itens.length) return false;
    return itens.every((p) => this.itensSelecionados().has(p.item_id));
  }

  limparSelecao(): void {
    this.itensSelecionados.set(new Set());
  }

  enviarSelecionados(): void {
    const ids = Array.from(this.itensSelecionados());
    if (!ids.length) return;
    this.enviandoSelecionados.set(true);
    this.mostrarAlerta('info', `Iniciando envio para ${ids.length} produto(s) selecionado(s)...`);

    this.afiliadosService.enviarSelecionados(ids, this.modoDryRun).subscribe({
      next: (res) => {
        this.enviandoSelecionados.set(false);
        this.mostrarAlerta('sucesso', res.mensagem || 'Envio iniciado com sucesso.');
        this.limparSelecao();
        setTimeout(() => this.carregarDados(), 3000);
      },
      error: () => {
        this.enviandoSelecionados.set(false);
        this.mostrarAlerta('erro', 'Falha ao solicitar envio dos produtos selecionados.');
      },
    });
  }

  excluirSelecionados(): void {
    const ids = Array.from(this.itensSelecionados());
    if (!ids.length) return;
    if (confirm(`Deseja realmente excluir os ${ids.length} produto(s) selecionado(s) e seus históricos de envio?`)) {
      this.excluindoSelecionados.set(true);
      this.afiliadosService.excluirSelecionados(ids).subscribe({
        next: (res) => {
          this.excluindoSelecionados.set(false);
          this.mostrarAlerta('sucesso', res.mensagem || `${ids.length} produto(s) excluído(s) com sucesso.`);
          this.limparSelecao();
          this.carregarDados();
        },
        error: () => {
          this.excluindoSelecionados.set(false);
          this.mostrarAlerta('erro', 'Falha ao excluir os produtos selecionados.');
        },
      });
    }
  }

  // Métodos de Upload de Arquivo
  onFileSelect(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files[0]) {
      this.processarArquivo(input.files[0]);
    }
  }

  onFileDrop(event: DragEvent): void {
    event.preventDefault();
    if (event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0]) {
      this.processarArquivo(event.dataTransfer.files[0]);
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
  }

  processarArquivo(file: File): void {
    if (!file.name.endsWith('.csv')) {
      this.mostrarAlerta('erro', 'Por favor, selecione um arquivo no formato CSV (.csv).');
      return;
    }
    this.arquivoUpload = file;
    this.nomeArquivoUpload = file.name;

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      this.gerarPreviewCSV(text);
    };
    reader.readAsText(file, 'utf-8');
  }

  gerarPreviewCSV(conteudo: string): void {
    const linhas = conteudo.split(/\r?\n/).filter((l) => l.trim().length > 0);
    if (linhas.length < 2) {
      this.previewUpload = [];
      return;
    }

    const primeiraLinha = linhas[0];
    const separador = primeiraLinha.includes(';') && !primeiraLinha.includes(',') ? ';' : ',';
    const parseLinha = (str: string) => {
      // Divide respeitando aspas simples ou duplas
      const regex = new RegExp(`(?:${separador}|\\r?\\n|^)(?:"([^"]*)"|'([^']*)'|([^"${separador}\\r\\n]*))`, 'gi');
      const matches: string[] = [];
      let match;
      while ((match = regex.exec(str)) !== null) {
        if (match.index === regex.lastIndex) regex.lastIndex++;
        matches.push((match[1] || match[2] || match[3] || '').trim());
      }
      return matches.length > 0 ? matches : str.split(separador).map((c) => c.replace(/['"]/g, '').trim());
    };

    const headers = parseLinha(primeiraLinha);
    this.previewUpload = [];

    for (let i = 1; i < Math.min(linhas.length, 6); i++) {
      const colunas = parseLinha(linhas[i]);
      const item: any = {};
      headers.forEach((h, idx) => {
        if (h) {
          item[h] = colunas[idx] || '';
        }
      });
      if (Object.keys(item).length > 0) {
        this.previewUpload.push(item);
      }
    }
  }

  confirmarUpload(): void {
    if (!this.arquivoUpload) return;
    this.uploading = true;

    const reader = new FileReader();
    reader.onload = (e) => {
      const conteudo = e.target?.result as string;
      this.afiliadosService.uploadCSV(this.nomeArquivoUpload, conteudo).subscribe({
        next: (res) => {
          this.uploading = false;
          this.mostrarAlerta(
            'sucesso',
            `Carga concluída! ${res.novos_inseridos} novos produtos inseridos, ${res.duplicados_ignorados} duplicados ignorados.`
          );
          this.cancelarUpload();
          this.setAba('produtos');
          this.carregarDados();
        },
        error: () => {
          this.uploading = false;
          this.mostrarAlerta('erro', 'Falha ao processar o arquivo CSV no servidor.');
        },
      });
    };
    reader.readAsText(this.arquivoUpload, 'utf-8');
  }

  cancelarUpload(): void {
    this.arquivoUpload = null;
    this.nomeArquivoUpload = '';
    this.previewUpload = [];
  }

  mostrarAlerta(tipo: 'sucesso' | 'erro' | 'info', texto: string): void {
    this.mensagemAlerta.set({ tipo, texto });
    setTimeout(() => {
      if (this.mensagemAlerta()?.texto === texto) {
        this.mensagemAlerta.set(null);
      }
    }, 5000);
  }

  getStatusClass(status?: string): string {
    switch (status) {
      case 'SUCESSO':
      case 'CONCLUIDO':
        return 'badge-sucesso';
      case 'PARCIAL':
        return 'badge-parcial';
      case 'FALHA':
        return 'badge-falha';
      default:
        return 'badge-pendente';
    }
  }
}
