# Diretrizes Universais de Engenharia, Segurança e Operação de IA (Google Antigravity & Graphify)

Este documento estabelece as diretrizes arquiteturais, operacionais e de segurança obrigatórias para agentes de IA e desenvolvedores no ciclo de vida deste repositório.

---

## 1. Protocolo de Inteligência Artificial (Google Antigravity & Graphify)

- **Análise Prévia com Graphify (Foco Estrito em Negócio):**
  - Toda demanda complexa, refatoração ou criação de feature deve ser precedida por uma consulta estruturada via Graphify (`graphify query` ou `query_graph`).
  - **Filtro de Ruído:** Isole e alimente o modelo apenas com os nós relacionados às regras de domínio, contratos de interface (APIs/DTOs) e entidades de negócio. Exclua do grafo artefatos de infraestrutura transitória, linters, testes de cobertura e arquivos de configuração operacional.
  - **Minimização de Contexto:** Forneça ao modelo apenas as fronteiras contratuais impactadas, evitando saturação de tokens e alucinações.

- **Execução Paralela Obrigatória (Concurrent Tasking):**
  - Sempre que uma tarefa envolver mais de uma camada desacoplada sem bloqueios diretos, decomponha o plano de execução em trilhas simultâneas:
    - **Trilha Backend:** Modelos de domínio, serviços, controladores e contratos de API.
    - **Trilha Frontend:** Interfaces visuais, gerenciamento de estado e clientes de consumo de API.
    - **Trilha Persistência & Schemas:** Migrações de banco de dados, schemas e definições de dados.
    - **Trilha Documentação & Testes:** Atualização de documentação de negócio e testes automatizados isolados.
  - Cada trilha deve operar com contratos de entrada e saída claramente definidos (DTOs/tipagens) antes da escrita do código.

---

## 2. Governança de Escopo, Arquivos e Higiene de Repositório

- **Confinamento Absoluto de Workspace:**
  - O agente deve atuar exclusivamente dentro da pasta raiz deste repositório. É terminantemente proibido ler, listar, modificar ou referenciar arquivos e diretórios externos sem autorização prévia explícita.

- **Proteção de Arquivos Sensíveis e Privados:**
  - Arquivos de anotações pessoais (ex.: `anotacoes.txt`, `drafts/`, `.private/`) ou variáveis de ambiente locais (`.env*`) não devem ser lidos, indexados ou manipulados sob hipótese alguma.

- **Higiene Rígida do `.gitignore`:**
  - O repositório deve manter expressamente fora do controle de versão todo arquivo irrelevante ao funcionamento do software em produção:
    - Artefatos de compilação e pastas de build.
    - Diretórios de dependências gerenciadas por pacotes.
    - Arquivos de configuração de IDEs e editores locais.
    - Logs, dumps de banco locais e arquivos temporários.
    - Arquivos do sistema operacional (`.DS_Store`, `Thumbs.db`).

- **Caminhos Portáveis:**
  - Utilize sempre caminhos relativos à raiz do projeto para qualquer documentação, script ou link, garantindo compatibilidade entre diferentes sistemas operacionais e contêineres.

---

## 3. Padrões de Arquitetura e Engenharia de Software

- **Documentação de Código com Propósito Funcional:**
  - Todas as classes de negócio, serviços, modelos e componentes de interface devem conter documentação explicativa (Javadoc, TSDoc ou padrão nativo da linguagem) indicando o propósito na regra de negócio, comportamento esperado e integrações.

- **Isolamento de Autenticação e Dados Sensíveis:**
  - Controladores e serviços de autenticação devem limitar-se exclusivamente ao ciclo de vida da sessão e identificadores mínimos de acesso.
  - É vedado trafegar dados cadastrais sensíveis, documentos pessoais ou atributos de negócio detalhados em rotas exclusivas de autenticação/tokens.

- **Zero Hardcode (Configuração Externa e Injeção de Dependências):**
  - É proibido declarar endereços de hosts, portas locais (`localhost`, `127.0.0.1`), chaves secretas ou URLs de dependências externas diretamente no código-fonte.
  - Todo parâmetro ambiental deve ser fornecido via variáveis de ambiente injetadas centralizadamente por clientes de configuração ou serviços de bootstrap.

---

## 4. Segurança de Aplicação e DevSecOps (OWASP)

- **Manipulação Segura de Uploads (OWASP File Upload Cheat Sheet):**
  - **Inspeção de Assinatura (Magic Bytes):** Não confie exclusivamente na extensão informada ou no header `Content-Type`. Valide os primeiros bytes do arquivo no servidor.
  - **Lista Branca Estrita:** Restrinja tipos permitidos unicamente aos formatos necessários para o negócio da funcionalidade.
  - **Mitigação de Path Traversal:** Rejeite ou sanitize o nome original do arquivo. Gere identificadores opacos criptograficamente seguros (como UUID v4) para persistência.
  - **Armazenamento Seguro:** Arquivos devem residir em serviços de Object Storage isolados, sem permissões de execução de scripts ou binários.
  - **Limites de Carga:** Configure tetos rígidos de tamanho máximo por arquivo e por requisição para mitigar ataques de negação de serviço (DoS).

- **Princípio do Menor Privilégio e Segregação de Ambientes:**
  - Backups de dados e credenciais em nuvem devem seguir estruturas hierárquicas claras e isoladas por ambiente (`dev/`, `staging/`, `prod/`), respeitando políticas de retenção e imutabilidade.

---

## 5. Ciclo de Vida de Execução, Containers e Decisão

- **Containers e Padronização:**
  - Todo container criado para o ambiente deve ser associado à rede padrão de contêineres do projeto e adotar explicitamente o timezone configurado (padrão: `America/Cuiaba`).
  - Priorize estratégias de hot reload em ambiente de desenvolvimento local. Reinicializações de contêineres devem ocorrer apenas mediante alterações de dependências, variáveis de ambiente ou migrações estruturais.

- **Análise de Causa Raiz e Autorização Prévia:**
  - Diante de falhas, erros de compilação ou regressões de testes, identifique e apresente a causa raiz no chat com alternativas de solução antes de aplicar alterações destrutivas ou de grande porte no código.

---

## 6. Especificações Deste Projeto (Preenchido)

- **Nome do Projeto:** `Afiliados Multi-Channel Hub`
- **Stack Backend:** `Python 3.14 / FastAPI / Uvicorn / SQLite3`
- **Stack Frontend:** `Angular 22 / TypeScript / CSS Vanilla Modular`
- **Banco de Dados & Migrações:** `SQLite (db/publicacoes.db gerenciado via db/controle.py)`
- **Diretório das Regras de Negócio:** `db/`, `shopee/`, `facebook/`, `instagran/`, `whatsapp/`, `produtos/`
- **Variáveis Chave de Integração:**
  - URL Base Backend: `http://localhost:8000`
  - URL Base Frontend: `http://localhost:4200`
  - WhatsApp Z-API: `ZAPI_ID`, `ZAPI_TOKEN`, `ZAPI_CLIENT_TOKEN`, `ZAPI_GROUP_ID`
  - Meta Graph API: `META_APP_ID`, `META_APP_SECRET`, `META_PAGE_ID`, `META_PAGE_TOKEN`, `INSTAGRAM_ACCOUNT_ID`
  - Shopee Open API: `SHOPEE_AFFILIATE_APP_ID`, `SHOPEE_AFFILIATE_SECRET`
- **Massa de Dados / Telefones para Teste:** `produtos/*.csv` e grupo WhatsApp `Dicas Shopee`