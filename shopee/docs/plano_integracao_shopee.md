# Plano de Integração: Shopee Affiliate Open API

## 1. Visão Geral da API

A integração com o Programa de Afiliados da Shopee Brasil é baseada em uma interface GraphQL via requisições HTTP POST seguras. Ao contrário de APIs REST tradicionais com múltiplos endpoints para cada recurso, todas as operações trafegam por uma única rota de entrada, distinguindo-se pelo payload GraphQL e pelas variáveis transmitidas.

* Endpoint único de produção: `https://open-api.affiliate.shopee.com.br/graphql`
* Método HTTP: `POST`
* Cabeçalho de conteúdo: `Content-Type: application/json`
* Formato do corpo da requisição: JSON compactado contendo campos `query` e opcionalmente `variables`
* Formato de resposta: JSON no padrão GraphQL, com chave `data` para sucessos e chave `errors` para inconsistências

## 2. Autenticação e Geração de Assinatura

A segurança das chamadas utiliza verificação criptográfica stateless por meio do cabeçalho HTTP `Authorization`. A Shopee valida a autenticidade do cliente calculando um hash SHA-256 no servidor e comparando com a assinatura enviada.

### Formato do Cabeçalho

```http
Authorization: SHA256 Credential={AppId},Timestamp={Timestamp},Signature={Signature}
```

Os elementos necessários para compor a autorização são:
* `Credential`: identificador da aplicação (`AppId`) gerado no painel da Shopee.
* `Timestamp`: carimbo de data e hora Unix atual, obrigatoriamente medido em segundos inteiros. Requisições com desvio de horário excessivo são rejeitadas.
* `Signature`: hash SHA-256 gerado em formato hexadecimal com letras minúsculas.

### Algoritmo de Cálculo da Assinatura

A assinatura é o resultado da aplicação do algoritmo SHA-256 sobre a concatenação exata e estrita de quatro elementos, sem delimitadores, barras ou espaços intermediários:

```
Signature = SHA256(AppId + Timestamp + Payload + Secret)
```

1. `AppId`: identificador público da aplicação parceira.
2. `Timestamp`: representação em string do carimbo Unix em segundos.
3. `Payload`: corpo exato da requisição enviado no HTTP POST (string JSON serializada sem espaços extras).
4. `Secret`: chave secreta disponibilizada pela Shopee, mantida confidencial no servidor cliente.

Uma inconsistência de espaçamento ou quebra de linha entre o payload serializado para cálculo do hash e o corpo efetivamente transmitido na rede invalidará a assinatura imediatamente.

## 3. Escopo das Operações Principais

A integração contempla três fluxos prioritários de negócio para automação da plataforma de afiliados.

### A. Geração de Links de Rastreamento (`generateShortLink`)

Operação do tipo mutação utilizada para converter links originais de páginas da Shopee em links de afiliados encurtados, injetando sub-identificadores (subIds) para mensuração de campanhas e origens de tráfego.

```graphql
mutation {
  generateShortLink(
    originUrl: "https://shopee.com.br/produto-exemplo-i.123.456",
    subIds: ["campanha_promo", "canal_telegram"]
  ) {
    shortLink
  }
}
```

### B. Catálogo e Ofertas de Produtos (`productOfferV2`)

Operação do tipo consulta (query) voltada à descoberta de ofertas ativas, produtos elegíveis à comissão, taxas vigentes e faixas de preço promocionais para sincronização ou vitrines locais.

```graphql
query FetchProducts($page: Int, $limit: Int) {
  productOfferV2(listType: 0, sortType: 2, page: $page, limit: $limit) {
    nodes {
      itemId
      productName
      price
      commissionRate
      commission
      productLink
      offerLink
      imageUrl
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

Operação para reconciliação financeira e acompanhamento de vendas geradas pelos links comissionados, retornando status de pedidos (pendente, aprovado, cancelado) e valores brutos e comissionados.

```graphql
query ConversionReport($startDate: String, $endDate: String, $page: Int) {
  conversionReport(startDate: $startDate, endDate: $endDate, page: $page) {
    nodes {
      purchaseTime
      orderId
      subIds
      itemPrice
      totalCommission
      orderStatus
    }
  }
}
```

## 4. Fases de Execução da Integração

### Fase 1: Configuração e Gerenciamento de Credenciais
1. Obtenção do `AppId` e `Secret` através da aprovação no painel de desenvolvedores do Programa de Afiliados Shopee.
2. Armazenamento das chaves em variáveis de ambiente (`.env`), sem expor credenciais no código-fonte.
3. Criação de rotina de verificação de integridade das credenciais no boot da aplicação.

### Fase 2: Módulo Core de Comunicação (Client Shopee)
1. Construção de classe ou módulo responsável por encapsular o cálculo de hash SHA-256 e montagem do cabeçalho `Authorization`.
2. Implementação de camada de serialização JSON canônica (sem caracteres de espaçamento desnecessários) para garantir paridade total entre o payload assinado e o payload enviado.
3. Tratamento de exceções e erros de protocolo GraphQL (diferenciação entre erro HTTP, erro de assinatura e erros semânticos na chave `errors`).

### Fase 3: Camada de Serviços de Negócio
1. Serviço de encurtamento: API interna para receber URL da Shopee, aplicar parâmetros analíticos e persistir o link gerado.
2. Serviço de ingestão de ofertas: rotina de consulta paginada a produtos em destaque para alimentar banco de dados ou fila de publicação.
3. Serviço de conferência de conversões: tarefa agendada (job de conciliação) para consultar periodicamente conversões faturadas e atualizar bases financeiras.

### Fase 4: Observabilidade e Resiliência
1. Implementação de log estruturado omitindo chaves secretas.
2. Monitoramento de limites de requisições por minuto impostos pela Shopee.
3. Política de repetição com backoff exponencial para falhas de rede transitórias.

## 5. Estrutura Recomendada no Projeto

A arquitetura no diretório `shopee/` deve separar as responsabilidades de criptografia, transporte e modelos de negócio:

* `shopee/client.py` (ou `client.js`): gerador de assinaturas, cabeçalhos e disparo HTTP POST.
* `shopee/services/link_service`: lógica de conversão e rastreamento de URLs.
* `shopee/services/catalog_service`: sincronização de ofertas e produtos comissionados.
* `shopee/services/report_service`: conciliação periódica de pedidos e comissões.
* `shopee/docs/`: documentações complementares e esquemas de dados.
