import { Component, OnInit, OnDestroy, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AfiliadosService } from './services/afiliados.service';
import {
  Produto,
  PaginacaoProdutos,
  ResumoEstatisticas,
  DetalheProdutoResposta,
  IntegracoesResposta,
  ShopeeOfertaItem,
  ShopeeConversoesResposta,
  ListaItem,
  EnvioStatusResposta,
} from './models/produto.model';

type AbaAtiva = 'produtos' | 'upload' | 'shopee' | 'conversoes' | 'dashboard' | 'integracoes';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
})
export class AppComponent implements OnInit, OnDestroy {
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
  filtroLista = 'TODAS';
  paginaAtual = 1;
  limitePorPagina = 10;
  carregandoLista = false;
  mensagemAlerta = signal<{ tipo: 'sucesso' | 'erro' | 'info'; texto: string } | null>(null);

  // Módulo de Listas
  listas = signal<ListaItem[]>([]);
  modalImportarListaAberto = signal<boolean>(false);
  modoLista: 'existente' | 'nova' | 'nenhuma' = 'existente';
  listaSelecionada = '';
  novaListaNome = '';
  salvandoImportacaoComLista = signal<boolean>(false);

  // Upload de CSV
  arquivoUpload: File | null = null;
  previewUpload: any[] = [];
  uploading = false;
  nomeArquivoUpload = '';

  // Inclusão Rápida por Link (ex: https://meli.la/2e9SRc8)
  novoLinkUrl = '';
  novoLinkLista = '';
  incluindoPorLink = signal<boolean>(false);

  // Monitoramento e Auto-Refresh em Tempo Real por Etapa
  envioStatus = signal<EnvioStatusResposta | null>(null);
  autoRefreshAtivo = signal<boolean>(false);
  private autoRefreshTimer: any = null;
  private ciclosSemAtividade = 0;

  // Seleção múltipla de produtos
  itensSelecionados = signal<Set<string>>(new Set());
  enviandoSelecionados = signal<boolean>(false);
  excluindoSelecionados = signal<boolean>(false);

  // Módulo Descoberta Shopee
  shopeeOfertas = signal<ShopeeOfertaItem[]>([]);
  shopeePagina = signal<number>(1);
  shopeeBusca = '';
  shopeeSortType = 2; // 2=vendas, 5=comissão, 1=relevância
  shopeeCarregando = signal<boolean>(false);
  shopeeImportando = signal<boolean>(false);
  shopeeHasNext = signal<boolean>(false);
  shopeeSelecionados = signal<Set<number>>(new Set());

  // Módulo Relatório de Conversões
  conversoesData = signal<ShopeeConversoesResposta | null>(null);
  conversoesCarregando = signal<boolean>(false);
  sincronizandoConversoes = signal<boolean>(false);
  conversoesBusca = signal<string>('');
  conversoesFiltroCanal = signal<string>('TODOS');
  conversoesFiltroStatus = signal<string>('TODOS');
  conversoesOrdenacao = signal<'recente' | 'maior_comissao' | 'maior_valor'>('recente');

  // Métricas Computadas e Filtros do Relatório
  conversoesFiltradas = computed(() => {
    const raw = this.conversoesData()?.conversoes || [];
    const busca = this.conversoesBusca().trim().toLowerCase();
    const canalFiltro = this.conversoesFiltroCanal();
    const statusFiltro = this.conversoesFiltroStatus();
    const ordenacao = this.conversoesOrdenacao();

    let filtradas = raw.filter((item) => {
      if (canalFiltro !== 'TODOS') {
        const itemCanal = (item.channel_type || '').toLowerCase();
        if (canalFiltro === 'whatsapp' && !itemCanal.includes('wa') && !itemCanal.includes('zap')) return false;
        if (canalFiltro === 'facebook' && !itemCanal.includes('fb') && !itemCanal.includes('facebook')) return false;
        if (canalFiltro === 'stories' && !itemCanal.includes('stories')) return false;
        if (canalFiltro === 'post' && !itemCanal.includes('post') && !itemCanal.includes('feed')) return false;
        if (canalFiltro === 'reels' && !itemCanal.includes('reels')) return false;
        if (canalFiltro === 'outros' && (itemCanal.includes('wa') || itemCanal.includes('fb') || itemCanal.includes('stories') || itemCanal.includes('post') || itemCanal.includes('reels'))) return false;
      }
      if (statusFiltro !== 'TODOS' && item.order_status !== statusFiltro) {
        return false;
      }
      if (busca) {
        const emNome = (item.item_name || '').toLowerCase().includes(busca);
        const emPedido = (item.order_id || '').toLowerCase().includes(busca);
        const emItem = String(item.item_id).toLowerCase().includes(busca);
        if (!emNome && !emPedido && !emItem) return false;
      }
      return true;
    });

    return [...filtradas].sort((a, b) => {
      if (ordenacao === 'maior_comissao') {
        return (b.item_commission || 0) - (a.item_commission || 0);
      }
      if (ordenacao === 'maior_valor') {
        return (b.item_price || 0) - (a.item_price || 0);
      }
      return (b.purchase_time || '').localeCompare(a.purchase_time || '');
    });
  });

  totalComissaoFiltrada = computed(() => {
    return this.conversoesFiltradas().reduce((acc, it) => acc + (it.item_commission || 0), 0);
  });

  totalVendasFiltrada = computed(() => {
    return this.conversoesFiltradas().reduce((acc, it) => acc + (it.item_price || 0), 0);
  });

  comissaoMediaPorPedido = computed(() => {
    const total = this.conversoesData()?.resumo?.total_pedidos || 0;
    const comissao = this.conversoesData()?.resumo?.total_comissao_reais || 0;
    return total > 0 ? comissao / total : 0;
  });

  ticketMedioVendas = computed(() => {
    const total = this.conversoesData()?.resumo?.total_pedidos || 0;
    const vendas = this.conversoesData()?.resumo?.total_vendas_reais || 0;
    return total > 0 ? vendas / total : 0;
  });

  taxaSucessoPedidos = computed(() => {
    const total = this.conversoesData()?.resumo?.total_pedidos || 0;
    const concluidos = this.conversoesData()?.resumo?.pedidos_por_status?.['COMPLETED'] || 0;
    return total > 0 ? Math.round((concluidos / total) * 100) : 0;
  });

  readonly canais = [
    { id: 'whatsapp', nome: 'WhatsApp', icone: '💬' },
    { id: 'facebook', nome: 'Facebook', icone: '📘' },
    { id: 'facebook_reels', nome: 'Facebook Reels', icone: '🎬' },
    { id: 'instagram_stories', nome: 'Stories', icone: '📱' },
    { id: 'instagram_post', nome: 'Post Feed', icone: '📸' },
    { id: 'instagram_reels', nome: 'Reels', icone: '🎬' },
  ];

  ngOnInit(): void {
    this.carregarDados();
    this.carregarIntegracoes();
    this.carregarListas();
    this.verificarEnvioEmAndamentoInicial();
  }

  ngOnDestroy(): void {
    this.pararAutoRefreshEnvio();
  }

  carregarDados(silencioso: boolean = false): void {
    this.carregarListaProdutos(silencioso);
    this.afiliadosService.carregarEstatisticas().subscribe({
      next: (stats) => this.estatisticas.set(stats),
    });
  }

  carregarListas(): void {
    this.afiliadosService.getListas().subscribe({
      next: (listas) => {
        this.listas.set(listas);
        if (listas.length > 0 && !this.listaSelecionada) {
          this.listaSelecionada = listas[0].nome;
        }
      },
      error: () => { },
    });
  }

  carregarListaProdutos(silencioso: boolean = false): void {
    if (!silencioso) {
      this.carregandoLista = true;
    }
    this.afiliadosService
      .getProdutos(this.paginaAtual, this.limitePorPagina, this.filtroStatus, this.buscaTermo, this.filtroLista)
      .subscribe({
        next: (data) => {
          this.produtosData.set(data);
          this.carregandoLista = false;
        },
        error: () => {
          if (!silencioso) {
            this.mostrarAlerta('erro', 'Falha ao conectar com o backend. Verifique se o servidor está ativo.');
          }
          this.carregandoLista = false;
        },
      });
  }

  incluirProdutoPorLink(): void {
    const url = (this.novoLinkUrl || '').trim();
    if (!url) {
      this.mostrarAlerta('erro', 'Cole o link do produto (ex: https://meli.la/2e9SRc8) para incluir.');
      return;
    }
    this.incluindoPorLink.set(true);
    this.afiliadosService.adicionarProdutoPorLink(url, this.novoLinkLista || undefined).subscribe({
      next: (res) => {
        this.incluindoPorLink.set(false);
        this.novoLinkUrl = '';
        this.mostrarAlerta('sucesso', res.mensagem || 'Produto incluído com sucesso a partir do link!');
        this.paginaAtual = 1;
        this.carregarDados();
        this.carregarListas();
      },
      error: (err) => {
        this.incluindoPorLink.set(false);
        const msg = err.error?.detail || 'Não foi possível extrair os dados do link informado.';
        this.mostrarAlerta('erro', msg);
      },
    });
  }

  verificarEnvioEmAndamentoInicial(): void {
    this.afiliadosService.getEnvioStatus().subscribe({
      next: (st) => {
        if (st && st.ativo) {
          this.envioStatus.set(st);
          this.iniciarAutoRefreshEnvio();
        }
      },
      error: () => {},
    });
  }

  iniciarAutoRefreshEnvio(): void {
    this.pararAutoRefreshEnvio();
    this.autoRefreshAtivo.set(true);
    this.ciclosSemAtividade = 0;

    const executarCiclo = () => {
      this.carregarDados(true);
      const detalheAtual = this.produtoSelecionado();
      if (detalheAtual?.produto?.item_id) {
        this.afiliadosService.getDetalheProduto(detalheAtual.produto.item_id).subscribe({
          next: (det) => this.produtoSelecionado.set(det),
          error: () => {},
        });
      }

      this.afiliadosService.getEnvioStatus().subscribe({
        next: (st) => {
          this.envioStatus.set(st);
          const algumEnviandoNaTabela = (this.produtosData()?.itens || []).some(
            (p) =>
              p.status_geral === 'ENVIANDO' ||
              Object.values(p.canais_status || {}).some((s) => s === 'ENVIANDO')
          );

          if (!st.ativo && !algumEnviandoNaTabela) {
            this.ciclosSemAtividade++;
            if (this.ciclosSemAtividade >= 2) {
              this.pararAutoRefreshEnvio();
              this.carregarDados(true);
              this.mostrarAlerta('sucesso', 'Envio finalizado! Todos os canais foram atualizados.');
            }
          } else {
            this.ciclosSemAtividade = 0;
          }
        },
        error: () => {},
      });
    };

    executarCiclo();
    this.autoRefreshTimer = setInterval(executarCiclo, 2000);
  }

  pararAutoRefreshEnvio(): void {
    if (this.autoRefreshTimer) {
      clearInterval(this.autoRefreshTimer);
      this.autoRefreshTimer = null;
    }
    this.autoRefreshAtivo.set(false);
  }

  obterLabelLink(url?: string): string {
    const u = (url || '').toLowerCase();
    if (u.includes('meli.la') || u.includes('mercadolivre')) {
      return 'Link Mercado Livre';
    }
    if (u.includes('shopee') || u.includes('shp.ee')) {
      return 'Link Shopee';
    }
    return 'Link Oferta';
  }

  onFiltroListaChange(novaLista: string): void {
    this.filtroLista = novaLista;
    this.paginaAtual = 1;
    this.carregarListaProdutos();
  }

  carregarIntegracoes(): void {
    this.afiliadosService.getIntegracoesStatus().subscribe({
      next: (res) => this.integracoes.set(res),
      error: () => { },
    });
  }

  setAba(aba: AbaAtiva): void {
    this.abaAtiva.set(aba);
    if (aba === 'shopee' && this.shopeeOfertas().length === 0) {
      this.carregarOfertasShopee();
    }
    if (aba === 'conversoes' && !this.conversoesData()) {
      this.carregarConversoes();
    }
  }

  carregarOfertasShopee(pagina: number = 1): void {
    this.shopeeCarregando.set(true);
    this.shopeePagina.set(pagina);
    this.afiliadosService
      .buscarOfertasShopee(this.shopeeBusca, this.shopeeSortType, pagina, 18)
      .subscribe({
        next: (res) => {
          this.shopeeOfertas.set(res.items || []);
          this.shopeeHasNext.set(res.has_next_page);
          this.shopeeCarregando.set(false);
          this.shopeeSelecionados.set(new Set());
        },
        error: (err) => {
          this.mostrarAlerta('erro', 'Falha ao buscar ofertas na Shopee API: ' + (err.error?.detail || err.message));
          this.shopeeCarregando.set(false);
        },
      });
  }

  onShopeeBuscaSubmit(): void {
    this.carregarOfertasShopee(1);
  }

  toggleSelecionarOferta(itemId: number): void {
    const atual = new Set(this.shopeeSelecionados());
    if (atual.has(itemId)) {
      atual.delete(itemId);
    } else {
      atual.add(itemId);
    }
    this.shopeeSelecionados.set(atual);
  }

  toggleSelecionarTodasOfertas(): void {
    const atual = this.shopeeSelecionados();
    const todas = this.shopeeOfertas();
    if (atual.size === todas.length && todas.length > 0) {
      this.shopeeSelecionados.set(new Set());
    } else {
      this.shopeeSelecionados.set(new Set(todas.map((o) => o.item_id)));
    }
  }

  importarOfertaUnica(oferta: ShopeeOfertaItem): void {
    this.shopeeImportando.set(true);
    this.afiliadosService.importarOfertasShopee([oferta]).subscribe({
      next: (res) => {
        this.shopeeImportando.set(false);
        const nomeCurto = oferta.product_name.length > 30 ? oferta.product_name.substring(0, 30) + '...' : oferta.product_name;
        this.mostrarAlerta('sucesso', `"${nomeCurto}" importado para o Hub!`);
        this.carregarDados();
        this.carregarListas();
      },
      error: (err) => {
        this.shopeeImportando.set(false);
        this.mostrarAlerta('erro', 'Erro ao importar oferta: ' + (err.error?.detail || err.message));
      },
    });
  }

  abrirModalImportarLista(): void {
    const selIds = this.shopeeSelecionados();
    if (selIds.size === 0) return;
    this.carregarListas();
    if (this.listas().length > 0) {
      this.modoLista = 'existente';
      if (!this.listaSelecionada) {
        this.listaSelecionada = this.listas()[0].nome;
      }
    } else {
      this.modoLista = 'nova';
    }
    this.novaListaNome = '';
    this.modalImportarListaAberto.set(true);
  }

  fecharModalImportarLista(): void {
    if (this.salvandoImportacaoComLista()) return;
    this.modalImportarListaAberto.set(false);
    this.novaListaNome = '';
  }

  confirmarImportacaoComLista(): void {
    const selIds = this.shopeeSelecionados();
    if (selIds.size === 0) return;

    let nomeLista: string | undefined = undefined;
    if (this.modoLista === 'existente') {
      nomeLista = this.listaSelecionada?.trim() || undefined;
      if (!nomeLista && this.listas().length > 0) {
        nomeLista = this.listas()[0].nome;
      }
    } else if (this.modoLista === 'nova') {
      const digitado = this.novaListaNome.trim();
      if (!digitado) {
        this.mostrarAlerta('erro', 'Por favor, informe o nome para a nova lista.');
        return;
      }
      nomeLista = digitado;
    }

    const ofertas = this.shopeeOfertas().filter((o) => selIds.has(o.item_id));
    this.salvandoImportacaoComLista.set(true);
    this.shopeeImportando.set(true);

    this.afiliadosService.importarOfertasShopee(ofertas, nomeLista).subscribe({
      next: (res) => {
        this.salvandoImportacaoComLista.set(false);
        this.shopeeImportando.set(false);
        this.modalImportarListaAberto.set(false);
        this.shopeeSelecionados.set(new Set());
        const msgLista = nomeLista ? ` vinculadas à lista "${nomeLista}"` : '';
        this.mostrarAlerta('sucesso', `${res.total_importados} oferta(s) importada(s) com sucesso${msgLista}!`);
        this.carregarDados();
        this.carregarListas();
      },
      error: (err) => {
        this.salvandoImportacaoComLista.set(false);
        this.shopeeImportando.set(false);
        this.mostrarAlerta('erro', 'Erro ao importar ofertas: ' + (err.error?.detail || err.message));
      },
    });
  }

  importarOfertasSelecionadas(): void {
    this.abrirModalImportarLista();
  }

  carregarConversoes(): void {
    this.conversoesCarregando.set(true);
    this.afiliadosService.getShopeeConversoes(50).subscribe({
      next: (data) => {
        this.conversoesData.set(data);
        this.conversoesCarregando.set(false);
      },
      error: () => {
        this.conversoesCarregando.set(false);
      },
    });
  }

  sincronizarConversoes(): void {
    this.sincronizandoConversoes.set(true);
    this.afiliadosService.sincronizarShopeeConversoes(50).subscribe({
      next: (res) => {
        this.sincronizandoConversoes.set(false);
        this.mostrarAlerta('sucesso', res.mensagem);
        this.carregarConversoes();
      },
      error: (err) => {
        this.sincronizandoConversoes.set(false);
        this.mostrarAlerta('erro', 'Falha ao sincronizar com Shopee: ' + (err.error?.detail || err.message));
      },
    });
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

  onImageError(event: Event): void {
    const target = event.target as HTMLImageElement;
    if (target) {
      target.style.display = 'none';
      const parent = target.parentElement;
      if (parent) {
        parent.classList.add('has-error');
      }
    }
  }

  reenviarProduto(itemId: string): void {
    this.mostrarAlerta('info', `Iniciando envio/reenvio de pendências para o item ${itemId}...`);
    this.afiliadosService.reenviarProduto(itemId).subscribe({
      next: (res) => {
        this.mostrarAlerta('sucesso', res.mensagem || 'Envio iniciado em segundo plano.');
        this.iniciarAutoRefreshEnvio();
      },
      error: () => this.mostrarAlerta('erro', 'Falha ao solicitar reenvio do item.'),
    });
  }

  reenviarTodasFalhas(): void {
    this.mostrarAlerta('info', 'Disparando rotina de reprocessamento em lote...');
    this.afiliadosService.reenviarTodosFalhas().subscribe({
      next: (res) => {
        this.mostrarAlerta('sucesso', res.mensagem || 'Reenvio em lote em andamento.');
        this.iniciarAutoRefreshEnvio();
      },
      error: () => this.mostrarAlerta('erro', 'Falha ao iniciar reenvio em lote.'),
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

    this.afiliadosService.enviarSelecionados(ids).subscribe({
      next: (res) => {
        this.enviandoSelecionados.set(false);
        this.mostrarAlerta('sucesso', res.mensagem || 'Envio iniciado com sucesso.');
        this.limparSelecao();
        this.iniciarAutoRefreshEnvio();
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
      case 'ENVIANDO':
        return 'badge-enviando';
      case 'PARCIAL':
        return 'badge-parcial';
      case 'FALHA':
        return 'badge-falha';
      default:
        return 'badge-pendente';
    }
  }

  formatarTaxaComissao(taxa: string | number | undefined): string {
    if (!taxa) return '0';
    const num = typeof taxa === 'number' ? taxa : parseFloat(taxa) || 0;
    return (num * 100).toFixed(0);
  }

  limparFiltrosConversoes(): void {
    this.conversoesBusca.set('');
    this.conversoesFiltroCanal.set('TODOS');
    this.conversoesFiltroStatus.set('TODOS');
    this.conversoesOrdenacao.set('recente');
  }

  obterInfoCanal(channelType?: string): { nome: string; icone: string; cor: string; bg: string } {
    const tipo = (channelType || '').toLowerCase();
    if (tipo.includes('wa') || tipo.includes('zap') || tipo.includes('wagrupo')) {
      return { nome: 'WhatsApp', icone: '💬', cor: '#16a34a', bg: '#dcfce7' };
    }
    if (tipo.includes('fb') || tipo.includes('facebook') || tipo.includes('fbfeed')) {
      return { nome: 'Facebook', icone: '📘', cor: '#2563eb', bg: '#dbeafe' };
    }
    if (tipo.includes('stories') || tipo.includes('igstories')) {
      return { nome: 'IG Stories', icone: '📱', cor: '#e11d48', bg: '#ffe4e6' };
    }
    if (tipo.includes('post') || tipo.includes('feed') || tipo.includes('igpost')) {
      return { nome: 'IG Post', icone: '📸', cor: '#9333ea', bg: '#f3e8ff' };
    }
    if (tipo.includes('reels') || tipo.includes('igreels')) {
      return { nome: 'IG Reels', icone: '🎬', cor: '#7c3aed', bg: '#ede9fe' };
    }
    return { nome: channelType ? channelType.toUpperCase() : 'Geral', icone: '🔗', cor: '#475569', bg: '#f1f5f9' };
  }

  exportarConversoesCSV(): void {
    const itens = this.conversoesFiltradas();
    if (!itens || itens.length === 0) {
      this.mostrarAlerta('info', 'Não há registros para exportar com os filtros atuais.');
      return;
    }
    const cabecalho = ['ID Pedido', 'ID Item', 'Produto', 'Canal', 'Valor Item (R$)', 'Comissão (R$)', 'Status', 'Data Compra'];
    const linhas = itens.map((c) => [
      `"${c.order_id || c.conversion_id}"`,
      `"${c.item_id}"`,
      `"${(c.item_name || '').replace(/"/g, '""')}"`,
      `"${c.channel_type || 'Geral'}"`,
      (c.item_price || 0).toFixed(2),
      (c.item_commission || 0).toFixed(2),
      `"${c.order_status}"`,
      `"${c.purchase_time}"`
    ]);
    const csvContent = '\uFEFF' + [cabecalho.join(';'), ...linhas.map((l) => l.join(';'))].join('\r\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    const dataStr = new Date().toISOString().split('T')[0];
    link.setAttribute('download', `shopee_conversoes_${dataStr}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    this.mostrarAlerta('sucesso', `${itens.length} conversão(ões) exportada(s) com sucesso para CSV.`);
  }
}
