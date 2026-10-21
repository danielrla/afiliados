/**
 * Modelos e DTOs de dados para o ecossistema de Afiliados.
 */

export interface CanaisStatus {
  whatsapp?: string;
  facebook?: string;
  instagram_stories?: string;
  instagram_post?: string;
  instagram_reels?: string;
  [key: string]: string | undefined;
}

export interface Produto {
  item_id: string;
  item_name: string;
  offer_link: string;
  product_link?: string;
  price?: string;
  codigo_artes?: string;
  status_geral: 'PENDENTE' | 'PARCIAL' | 'CONCLUIDO' | 'FALHA';
  criado_em?: string;
  atualizado_em?: string;
  pasta_artes?: string;
  canais_status: CanaisStatus;
}

export interface HistoricoLog {
  id: number;
  item_id: string;
  canal: string;
  status: string;
  id_externo?: string;
  mensagem_erro?: string;
  caminho_imagem?: string;
  data_envio: string;
}

export interface DetalheProdutoResposta {
  produto: Produto;
  logs: HistoricoLog[];
}

export interface ResumoEstatisticas {
  total_produtos: number;
  concluidos: number;
  parciais: number;
  falhas: number;
  pendentes: number;
  canais: {
    [canal: string]: {
      SUCESSO: number;
      FALHA: number;
      PENDENTE: number;
    };
  };
}

export interface PaginacaoProdutos {
  total: number;
  pagina: number;
  limite: number;
  total_paginas: number;
  itens: Produto[];
}

export interface UploadResultado {
  total_lidos: number;
  novos_inseridos: number;
  duplicados_ignorados: number;
  erros: string[];
}

export interface IntegracaoStatus {
  configurado: boolean;
  mensagem: string;
}

export interface IntegracoesResposta {
  whatsapp: IntegracaoStatus;
  facebook: IntegracaoStatus;
  instagram: IntegracaoStatus;
  shopee: IntegracaoStatus;
}

export interface ShopeeOfertaItem {
  item_id: number;
  product_name: string;
  price: string;
  commission_rate: string;
  commission: string;
  sales: number;
  rating_star: number;
  image_url: string;
  product_link: string;
  offer_link: string;
  shop_name: string;
  shop_id: number;
  selecionado?: boolean;
}

export interface ShopeeOfertasResposta {
  items: ShopeeOfertaItem[];
  page: number;
  limit: number;
  has_next_page: boolean;
}

export interface ShopeeConversaoItem {
  conversion_id: string;
  order_id: string;
  item_id: string;
  item_name: string;
  item_price: number;
  item_commission: number;
  order_status: string;
  channel_type?: string;
  purchase_time: string;
  criado_em: string;
}

export interface ShopeeConversoesResposta {
  resumo: {
    total_pedidos: number;
    total_comissao_reais: number;
    total_vendas_reais: number;
    pedidos_por_status: { [status: string]: number };
    comissao_por_canal: { channel_type: string; qtd: number; comissao: number }[];
  };
  conversoes: ShopeeConversaoItem[];
}
