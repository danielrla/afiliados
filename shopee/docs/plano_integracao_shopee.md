# Plano de Integração: Shopee Affiliate Open API

## 1. Visão Geral da API

A integração com o Programa de Afiliados da Shopee Brasil é baseada em uma interface GraphQL via requisições HTTP POST seguras. Ao contrário de APIs REST tradicionais com múltiplos endpoints para cada recurso, todas as operações trafegam por uma única rota de entrada, distinguindo-se pelo payload GraphQL e pelas variáveis transmitidas.

* Endpoint único de produção: `https://open-api.affiliate.shopee.com.br/graphql`
* Método HTTP: `POST`
* Cabeçalho de conteúdo: `Content-Type: application/json`
* Formato do corpo da requisição: JSON canônico compactado contendo campos `query` e opcionalmente `variables`
* Formato de resposta: JSON no padrão GraphQL, com chave `data` para sucessos e chave `errors` para inconsistências

## 2. Autenticação e Geração de Assinatura

A segurança das chamadas utiliza verificação criptográfica stateless por meio do cabeçalho HTTP `Authorization`. A Shopee valida a autenticidade do cliente calculando um hash SHA-256 no servidor e comparando com a assinatura enviada.

### Formato do Cabeçalho

```http
Authorization: SHA256 Credential={AppId},Timestamp={Timestamp},Signature={Signature}
```

Os elementos necessários para compor a autorização são:
* `Credential`: identificador da aplicação (`AppId`) gerado no painel da Shopee.
* `Timestamp`: carimbo de data e hora Unix atual, medido em segundos inteiros.
* `Signature`: hash SHA-256 gerado em formato hexadecimal com letras minúsculas.

### Algoritmo de Cálculo da Assinatura

```
Signature = SHA256(AppId + Timestamp + Payload + Secret)
```

1. `AppId`: identificador público da aplicação parceira.
2. `Timestamp`: representação em string do carimbo Unix em segundos.
3. `Payload`: corpo exato da requisição enviado no HTTP POST (string JSON serializada com separadores canônicos sem espaços extras).
4. `Secret`: chave secreta disponibilizada pela Shopee, mantida confidencial no servidor cliente.

## 3. Especificação das Operações GraphQL Implementadas

### A. Geração de Links de Rastreamento (`generateShortLink`)

Converte links originais de páginas da Shopee em links encurtados de afiliado, injetando sub-identificadores (`subIds`) para mensuração de campanhas e origens de tráfego.

**Restrição Crítica Validada:** O parâmetro `subIds` aceita exclusivamente caracteres alfanuméricos (`a-z`, `0-9`). A presença de sublinhados (`_`), hífens ou caracteres especiais gera erro `11001: Params Error : invalid sub id`.

```graphql
mutation GenerateShortLink($input: ShortLinkInput!) {
  generateShortLink(input: $input) {
    shortLink
  }
}
```

Mapeamento de subIds adotado no projeto:
* WhatsApp: `wagrupo`
* Facebook Page: `fbfeed`
* Instagram Stories: `igstories`
* Instagram Post: `igpost`
* Instagram Reels: `igreels`

### B. Catálogo e Ofertas de Produtos (`productOfferV2`)

Consulta produtos elegíveis a comissão com filtros avançados.
**Atenção Operacional:** Os argumentos opcionais não devem ser transmitidos com valor `null` na requisição, pois a Shopee interpreta `null` como filtro restritivo. A query deve ser construída dinamicamente contendo apenas os argumentos fornecidos.

```graphql
query FetchProductOffers($page: Int, $limit: Int, $sortType: Int, $keyword: String, $itemId: Int, $listType: Int) {
  productOfferV2(page: $page, limit: $limit, sortType: $sortType, keyword: $keyword, itemId: $itemId, listType: $listType) {
    nodes {
      itemId
      productName
      price
      commissionRate
      commission
      sales
      ratingStar
      imageUrl
      productLink
      offerLink
      shopName
      shopId
      periodStartTime
      periodEndTime
    }
    pageInfo {
      page
      limit
      hasNextPage
    }
  }
}
```

### C. Relatórios de Desempenho e Conversão (`conversionReport`)

Reconciliação financeira e acompanhamento de vendas geradas pelos links comissionados.

```graphql
query FetchConversionReport($purchaseTimeStart: Int, $purchaseTimeEnd: Int, $limit: Int, $scrollId: String) {
  conversionReport(purchaseTimeStart: $purchaseTimeStart, purchaseTimeEnd: $purchaseTimeEnd, limit: $limit, scrollId: $scrollId) {
    nodes {
      conversionId
      purchaseTime
      conversionStatus
      grossCommission
      totalCommission
      netCommission
      orders {
        orderId
        orderStatus
        items {
          itemId
          itemName
          itemPrice
          itemCommission
          itemTotalCommission
          channelType
        }
      }
    }
    pageInfo {
      limit
      hasNextPage
      scrollId
    }
  }
}
```

## 4. Contratos de DTOs e Arquitetura no Backend

### DTOs Implementados em `shopee/client.py`:
* `ShopeeOfferItem`: entidade representativa do produto/oferta.
* `ShopeeOfferSearchResult`: container paginado com nós e flags de navegação.
* `ShopeeConversionItem`: registro individual de item faturado/comissionado.

### Endpoints REST Expostos em `server.py`:
* `GET /api/shopee/ofertas`: listagem de ofertas em tempo real.
* `POST /api/shopee/importar-ofertas`: inclusão em lote na tabela `produtos`.
* `GET /api/shopee/conversoes`: resumo financeiro e listagem de conversões salvas.
* `POST /api/shopee/sincronizar-conversoes`: disparo de job para reconciliação contábil com a Shopee.
* `POST /api/shopee/gerar-link`: serviço interno de encurtamento com atribuição por canal.

### Estrutura de Banco de Dados (`db/controle.py`):
* Tabela `shopee_conversoes`: persistência histórica de compras faturadas com `conversion_id` único.
* Coluna `link_rastreado` em `canais_status`: registro do link específico enviado em cada rede social.
