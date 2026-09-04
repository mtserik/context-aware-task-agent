# Project Maeve: Context-Aware Knowledge & Task Orchestrator
## Technical Specification & High-Context LLM Onboarding Blueprint

This document serves as the master context ledger for **Project Maeve** (working name). It documents the complete evolution of the project from inception to its modular architectural design. It is specifically engineered to onboard advanced LLM interfaces and Autonomous Agents into the workspace.

---

## 0. Engineering Charter & AI Operating System (Staff Persona)

> **Mandato Obrigatório para qualquer Agente ou Engenheiro interagindo neste repositório:**
> Atue com o rigor técnico, visão holística e padrões de excelência de um **Staff Software Engineer & Staff Data Scientist**.
> Não aceite soluções paliativas ("quick-and-dirty fixes"), cosméticas (como fragmentação ingênua de arquivos sem evolução do modelo de objetos) ou código espaguete acoplado a frameworks. Avalie toda solução a partir dos **primeiros princípios** (*first-principles reasoning*), garantindo arquitetura limpa, modelagem orientada a objetos (POO), rigor matemático e máxima eficiência computacional.

### 0.1 Princípios de Engenharia de Software & POO
1. **Modelagem Orientada a Objetos (POO) & SOLID:**
   - **Single Responsibility (SRP):** Cada classe e módulo possui uma única razão para mudar. Um componente não deve misturar sanitização de mensagens, conexão com I/O, formatação de prompt e inferência de modelo.
   - **Open/Closed (OCP):** Aberto para extensão, fechado para modificação. Novos provedores de tarefas, vetores ou memória devem ser implementados via polimorfismo e interfaces bem definidas, nunca por cadeias de `if/else`.
   - **Liskov Substitution (LSP) & Interface Segregation (ISP):** Crie protocolos e interfaces enxutos (`typing.Protocol` / ABC). Componentes clientes não devem depender de métodos que não utilizam.
   - **Dependency Inversion (DIP):** Módulos de alto nível (orquestradores de agente) não devem depender diretamente de detalhes concretos de baixo nível (APIs REST específicas). Devem depender de abstrações de repositório e serviços de domínio.
2. **Clean Architecture & Hexagonal Ports/Adapters:**
   - **Camada de Domínio / Negócio (Core Domain):** Lógica pura de negócio totalmente desacoplada de frameworks (LangGraph, FastAPI, FastMCP). Criar uma hierarquia de subtarefas, calcular time-blocking, formatar notas com metadados ou consolidar decisões são regras puras de domínio.
   - **Camada de Adaptadores (Inbound & Outbound):**
     - *Inbound Adapters (Drivers):* LangGraph `@tool`, FastMCP `@mcp.tool()`, Telegram Handlers, rotas FastAPI.
     - *Outbound Adapters (Driven):* Clientes HTTP (TickTick REST/MCP), Qdrant Vector Client, Supabase Connection Pool, Git CLI Subprocess.
   - **Regra de Ouro:** **NUNCA** embutir anotações de framework de interface (`@tool`, `@app.post`, `@mcp.tool`) com a implementação da regra de negócio. A ferramenta de framework deve ser apenas um adaptador fino de 3 a 5 linhas chamando o método de domínio correspondente.
3. **Padrões de Design Estruturais e Criacionais:**
   - **Facade / Service Layer:** Unifica e simplifica fluxos complexos para os orquestradores.
   - **Repository / Registry:** Isola o ciclo de vida, persistência e instâncias lazy singletons.
   - **Adapter Pattern:** Normaliza contratos heterogêneos (ex: TickTick REST vs TickTick MCP JSON-RPC).
   - **Strategy Pattern:** Permite trocar dinamicamente algoritmos de busca (semântica vs híbrida vs exata) e roteamento de modelos.

### 0.2 Rigor Matemático, Ciência de Dados & RAG
1. **Espaço Vetorial e Álgebra Linear:**
   - Vetores de embedding (ex: `text-embedding-3-small`, 1536 dimensões) residem na hiperesfera $\mathbb{R}^{1536}$. O produto escalar normalizado (Cosine Similarity) quantifica a proximidade semântica:
     $$\text{sim}(\mathbf{u}, \mathbf{v}) = \frac{\mathbf{u} \cdot \mathbf{v}}{\|\mathbf{u}\|_2 \|\mathbf{v}\|_2}$$
   - **Filtro de Ruído & Limiares:** Buscas vetoriais ingênuas que sempre retornam os $k$ primeiros vizinhos degradam o raciocínio do modelo ao injetar ruído irrelevante. Utilize limiares de corte de score (*similarity score threshold*) e filtre consultas onde a variância de similaridade não justifique contexto externo.
2. **Chunking Semântico & Densidade Informacional:**
   - O chunking de conhecimento não deve ser um truncamento cego por caracteres. Deve respeitar fronteiras sintáticas do Markdown (árvore de cabeçalhos H1/H2/H3, blocos de código atômicos, tabelas) mantendo metadados essenciais (caminho relativo, tags, frontmatter).
3. **Economia de Tokens, Atenção e Complexidade Algorítmica:**
   - A complexidade do mecanismo de Self-Attention cresce com o tamanho da janela de contexto ($O(N^2)$ a $O(N \log N)$).
   - Injetar dezenas de ferramentas simultâneas no prompt consome tokens a cada turno e induz *Tool Bleed* / confusão de parâmetros. A seleção de ferramentas deve ser determinística e fundamentada em **Intent-Based Dynamic Tool Routing**.
4. **Tratamento de Incerteza e Probabilidade:**
   - O roteamento de intenção e complexidade deve operar com faixas de confiança probabilística. Em situações de alta entropia ou ambiguidade, o sistema deve adotar comportamentos conservadores e explicáveis com fallbacks predeterminados.

### 0.3 Diretrizes para Máxima Performance e Velocidade de Desenvolvimento
- **Tipagem Estrita Estática (Strict Type Annotations):** 100% do código deve ser tipado com `typing`, `pydantic.BaseModel` e `TypedDict`. Zero `Any` sem justificativa explícita.
- **Proteção Absoluta do Event Loop Assíncrono:** Nenhuma operação de rede, filesystem síncrono ou subprocesso pode travar o event loop principal. Use `asyncio.to_thread` ou clientes nativamente assíncronos.
- **Connection Pooling & Idempotência:** Conexões de rede persistentes com timeouts estritos. Operações de mutação devem possuir características idempotentes sempre que viável.
- **Testabilidade como Cidadão de Primeira Classe:** A arquitetura deve permitir testar a lógica de negócios em milissegundos com mocks leves injetados, sem necessidade de levantar serviços externos ou containers.

---

## 1. Project Vision & Core Objective

The goal of Project Maeve is to develop a highly personalized, autonomous, cross-platform productivity engine. Unlike standard reactive chatbots, Maeve acts as a **Memory-Augmented Autonomous Agent** that bridges semantic knowledge management with operational real-time execution.

### Key Workflows (The Two-Way Street Paradigm)
*   **Semantic Memory (Read/Write RAG):** The agent connects directly to the user's personal knowledge base (**Obsidian Vault**). It performs semantic searches over vectorized Markdown notes to answer context-heavy questions (Retrieval-Augmented Generation) and can autonomously write back, append updates, or format new insights directly into the Vault.
*   **Operational Execution (Action Layer):** The agent connects to the user's task manager (**TickTick**) via REST APIs or the Model Context Protocol (MCP) to dynamically list, create, schedule, modify, or close out daily tasks and routine reminders.

### Why Obsidian? (Privacy & Control)
The project migrated from Notion to Obsidian to prioritize:
*   **Data Sovereignty:** Local-first storage means you own your data; no proprietary cloud lock-in.
*   **Git-Powered Versioning:** Every change made by the AI is committed to a private Git repository, providing a full audit trail and easy rollbacks.
*   **Performance:** Local file access is significantly faster than external API calls, improving RAG latency.
*   **Longevity:** Plain Markdown files ensure your knowledge remains accessible for decades, independent of any single software vendor.

---

## 2. System Design & Architecture

To maintain strict **Dev-Prod Parity**, the project is split into two distinct execution lifecycles using decoupled services.

### Phase 1: Containerized Local MVP (Current Implementation)
The local development stack isolates compute and data services locally using **Docker Compose** to mimic cloud operations perfectly without infrastructure overhead.

[ Your Local Machine ]
                        │
          ▲▲▲─── Docker Compose ───▲▲▲
          │                          │
          ▼                          ▼
┌───────────────────┐      ┌───────────────────┐
│  CONTAINER 1      │      │  CONTAINER 2      │
│  Agent App        │◄────►│  Local Vector DB  │
│  (FastAPI +       │      │  (Qdrant DB)      │
│   LangGraph)      │      │                   │
└───────────────────┘      └───────────────────┘
          ▲
          │ (HTTPS Requests via Internet)
          ▼
┌──────────────────────────────────────────────┐
│              EXTERNAL APIs                   │
│  - Obsidian Vault (via Private Git Repo)     │
│  - OpenAI API (Embeddings & LLM Brain)       │
│  - TickTick API (Task Management)            │
└──────────────────────────────────────────────┘

*   **App Engine (`agent-app` container):** Runs Python 3.11-slim, wrapping a **FastAPI** web server around a **LangGraph** orchestration loop. Utilizes `uvicorn --reload` coupled with a Docker volume mount (`./src:/app/src`) for immediate hot-reloading during development.
*   **Vector Database (`local-vector-db` container):** Runs a local instance of **Qdrant**, exposing endpoints at ports `6333` and `6334`. Data is persistently volumed to the host machine via `qdrant_storage` to ensure vector indexes survive container lifecycles.
*   **Git-Sync Knowledge Base:** The agent clones and maintains a local copy of the user's **Obsidian Vault**. It performs `git pull` to stay in sync with the user's latest notes and `git push` to save insights generated by the agent back to the Vault.

### Phase 2: Production Cloud Architecture (Future Scalability)
Once verified locally, the application shifts seamlessly to a cloud environment by altering runtime environment variables.

*   **Interface Layer:** Shipped as a **Telegram Bot** backend. Messages (text and audio voice notes) strike a public FastAPI webhook endpoint. Audio files are natively processed through OpenAI's **Whisper API** for speech-to-text transcription before agent analysis.
*   **Compute:** Hosted inside the identical Docker wrapper on serverless container infrastructure such as **Railway** or **Render**.
*   **Cloud Data Core:** Migrated to a centralized cloud instance of **Supabase (PostgreSQL)**:
    *   *Relational Memory:* Standard relational tables store LangGraph session checkpoints to track continuous conversational state and thread history across multiple turns.
    *   *Vector Memory:* Uses the `pgvector` extension to store permanent production embeddings.

---

## 3. Semantic Engine Logic & Domain-Driven Orchestration

A tomada de decisão da Maeve é fundamentada em **Domain-Driven Architecture** e **Intent-Based Dynamic Tool Routing**, eliminando tanto scripts condicionais rígidos quanto o desperdício computacional de injetar dezenas de ferramentas simultâneas no prompt.

### 3.1 O Pipeline de Decisão (Do Usuário à Execução)
1. **Classificação de Intenção & Complexidade (Router Node):**
   - Recebe a mensagem do usuário e aplica a heurística Fast-Path ($O(1)$) para saudações e comandos triviais.
   - Em caso de mensagens informacionais/operacionais, classifica:
     - `complexity`: $1$ a $5$ (determina a capacidade do modelo: `fast_model` vs `smart_model`).
     - `domain`: `tasks` (TickTick), `knowledge` (Obsidian), `search` (Web), `reminders` (Supabase/TG) ou `chat` (sem ferramentas).
2. **Injeção Restrita de Ferramentas (Dynamic Tool Binding):**
   - Ao invés de expor todas as 22 ferramentas (que degradam a atenção do transformador e induzem *Tool Bleed*), o modelo recebe **apenas o subconjunto de ferramentas correspondente ao domínio ativo** (geralmente de 2 a 5 ferramentas).
3. **Resolução de Contexto & Compilação de Prompt (Context Pipeline):**
   - O enriquecimento de contexto é modular: RAG vetorial seletivo (filtrado por similaridade semântica), consciência temporal e dados de perfil do usuário.
4. **Execução Segura & Loop ReAct Sanitizado:**
   - As ferramentas do LangGraph invocam a **Camada de Domínio Pura**, garantindo que regras de negócio sejam agnósticas da interface.
   - O histórico de mensagens é higienizado contra mensagens órfãs e violações de contrato das APIs de chat.

---

## 4. Workspace Registry & File Tree

```text
context-aware-task-agent/
├── .dockerignore
├── .env.example
├── .gitignore
├── AGENTS.md              # Master system design documentation (This file)
├── Dockerfile
├── LICENSE
├── README.md
├── docker-compose.yml
├── obsidian_vault/        # Git-synced Obsidian Vault (local mount)
├── requirements.txt
└── src/
    ├── main.py            # FastAPI Composition Root (lifespan, router mounting)
    ├── cli.py             # Rich terminal CLI client (v0.4.0)
    ├── debug_tasks.py     # TickTick debugging utility
    ├── setup_ticktick.py  # OAuth2 setup helper
    ├── domain/            # Pure Core Business Domain Layer (Hexagonal Core)
    │   ├── __init__.py    # Domain exports (TaskResult, KnowledgeResult, etc.)
    │   ├── models.py      # Domain DTOs, Enums and Result contracts
    │   ├── tasks.py       # TaskDomainService (TickTick pure domain rules)
    │   ├── knowledge.py   # KnowledgeDomainService (Obsidian pure domain rules)
    │   ├── reminders.py   # ReminderDomainService (Domain scheduling rules)
    │   ├── search.py      # SearchDomainService (Web search & research domain)
    │   └── temporal.py    # TemporalDomainService (Strict timezone & relative date resolution)
    ├── agent/
    │   ├── engine.py      # MaeveAgent: LangGraph StateGraph & Dynamic Tool Routing
    │   ├── prompts.py     # System prompt templates & persona definition
    │   ├── state.py       # AgentState TypedDict & IntentDomain definition
    │   └── tools/         # Inbound Adapters (Thin LangGraph @tool wrappers)
    │       ├── __init__.py        # Registry & dynamic tool binding by intent
    │       ├── task_tools.py      # Thin adapters calling TaskDomainService
    │       ├── knowledge_tools.py # Thin adapters calling KnowledgeDomainService
    │       ├── reminder_tools.py  # Thin adapters calling ReminderDomainService
    │       └── search_tools.py    # Thin adapters calling SearchDomainService
    ├── api/               # Modular REST endpoints (Inbound HTTP Adapters)
    │   ├── __init__.py    # Router exports
    │   ├── deps.py        # API key authentication dependencies
    │   └── routes/
    │       ├── __init__.py # Aggregated API router
    │       ├── health.py   # GET / and GET /health
    │       ├── chat.py     # POST /chat
    │       └── sync.py     # POST /sync/obsidian
    ├── models/
    │   └── schemas.py     # Pydantic request/response models
    ├── services/
    │   ├── database.py    # Supabase/Postgres: pool, checkpointer, reminders
    │   ├── obsidian.py    # Obsidian Vault: Git sync, CRUD, frontmatter
    │   ├── registry.py    # Shared singleton service registry & dependency decoupling
    │   ├── reminder_worker.py  # Background worker for scheduled reminders
    │   ├── search.py      # Tavily web search & deep research
    │   ├── telegram_bot.py    # Telegram interface: text, voice, PDFs
    │   ├── ticktick.py    # TickTick REST API + MCP JSON-RPC client
    │   └── vector_db.py   # Qdrant async client: embeddings & search
    └── test/
        ├── test_bugfixes_regression.py # Comprehensive regression test suite
        └── test_domain_services.py     # Domain services & dynamic tool routing suite
```

---

## 5. Code Quality Audit & Resolution Status

> Full audit performed on 2026-09-03 and remediated on branch `fix/critical-bugs-audit`.

### 5.1 Architecture & Design Issues

| ID | Severity | File(s) | Issue | Status & Fix |
|:---|:---------|:--------|:------|:-------------|
| A1 | 🔴 High | `engine.py` | **God Module & Monolithic Tool Bleed.** 613 linhas acumulando 22 ferramentas acopladas ao LangGraph, RAG, sanitização de histórico e orquestração. Provoca Tool Bleed e inviabiliza reuso no MCP. | ✅ **Resolvido (Sprints 6, 7, 8).** Arquitetura Limpa implementada: Camada de Domínio Pura (`src/domain/`), adaptadores finos `@tool` (`src/agent/tools/`), e Intent-Based Dynamic Tool Routing no `engine.py`. Redução de 613 para 264 linhas e economia de ~88% de tokens de ferramentas por turno (de ~3.500 para ~400 tokens). |
| A2 | 🔴 High | `engine.py`, `main.py` | **Duplicate service instantiation.** Stateful singletons duplicated. | ✅ **Resolvido.** Criado `src/services/registry.py` com singletons lazy desacoplados. |
| A3 | 🟡 Medium | `telegram_bot.py` | **Circular imports.** `from src.main import ...` inside methods. | ✅ **Resolvido.** `telegram_bot.py` consome dependências via `registry.py`. |
| A4 | 🟡 Medium | `api/` directory | **Empty module.** FastAPI routes inline in `main.py`. | ✅ **Resolvido (Sprint 9).** Rotas REST modularizadas em `src/api/routes/` (`health.py`, `chat.py`, `sync.py`) com injeção de dependências em `deps.py`. `main.py` reduzido a 83 linhas como Composition Root. |
| A5 | 🟡 Medium | `state.py` | **`current_intent` field unused.** Defined in `AgentState`. | ✅ **Resolvido (Sprint 7).** `IntentDomain` tipado estritamente e `current_intent` ativamente preenchido pelo router para orquestrar a injeção dinâmica de ferramentas. |
| A6 | 🟢 Low | `notion.py` | **Dead code.** Notion migration artifact. | ✅ **Resolvido.** Arquivo e dependências removidos. |
| A7 | 🟢 Low | `chat.py` | **Superseded by `cli.py`.** Legacy sync chat client. | ✅ **Resolvido.** Arquivo removido via Git. |
| A8 | 🔴 High | `prompts.py`, `engine.py` | **Monolithic Static Persona & Prompt Bloat.** Prompt estático monolítico para todos os modelos, sobrecarregando modelos rápidos de execução e subaproveitando a capacidade cognitiva de modelos de fronteira. | ✅ **Resolvido (Sprint 10).** Arquitetura de Persona Dinâmica Assimétrica: `FAST_PROMPT_TEMPLATE` condicionado com 3 few-shots de referência (dev peer brasileira) para GPT-5.6 Luna e `SMART_PROMPT_TEMPLATE` ancorado em 4 Pilares Comportamentais (Curva Circadiana, Anti-Sycophancy/Devil's Advocate, Continuidade Episódica e Curadoria Ativa de Segundo Cérebro) para Claude Sonnet, resolvidos dinamicamente por `get_system_prompt(tier=...)`. |

### 5.2 Security & Reliability Issues

| ID | Severity | File(s) | Issue | Status & Fix |
|:---|:---------|:--------|:------|:-------------|
| S1 | 🔴 High | `obsidian.py` | **`StrictHostKeyChecking=no`** disables SSH verification. | ✅ **Resolvido.** Atualizado para `StrictHostKeyChecking=accept-new` com known_hosts. |
| S2 | 🔴 High | `engine.py` | **Hardcoded model names.** No env override. | ✅ **Resolvido.** Migrado para variáveis `MAEVE_FAST_MODEL` e `MAEVE_SMART_MODEL`. |
| S3 | 🟡 Medium | `main.py` | **Deprecated FastAPI lifecycle events.** | ✅ **Resolvido.** Migrado para `@app.lifespan` context manager. |
| S4 | 🟡 Medium | `vector_db.py` | **Unstable point IDs.** Collision/negative hash risk. | ✅ **Resolvido.** Migrado para `uuid.uuid5(NAMESPACE_URL, key)`. |
| S5 | 🟡 Medium | `vector_db.py` | **Sync embedding call in async context.** | ✅ **Resolvido.** Utiliza `aembed_documents()` e `aembed_query()`. |
| S6 | 🟢 Low | `search.py` | **Sync Tavily client in async method.** | ✅ **Resolvido.** Execução assíncrona desacoplada via `asyncio.to_thread`. |
| S7 | 🟢 Low | `requirements.txt` | **Unpinned dependencies.** Non-reproducible builds. | ✅ **Resolvido.** Todas as dependências pinadas estritamente. |
| S8 | 🟢 Low | `requirements.txt` | **`requests` is unused.** | ✅ **Resolvido.** Removido do requirements.txt. |

### 5.3 Performance & Operational Issues

| ID | Severity | File(s) | Issue | Status & Fix |
|:---|:---------|:--------|:------|:-------------|
| P1 | 🟡 Medium | `engine.py` | **Router LLM call on every message.** | ✅ **Resolvido.** Heurística Fast-Path pula LLM para saudações e mensagens curtas. |
| P2 | 🟡 Medium | `obsidian.py` | **Blocking subprocess in async service.** | ✅ **Resolvido.** Operações Git encapsuladas em `asyncio.to_thread`. |
| P3 | 🟡 Medium | `ticktick.py` | **New `httpx.AsyncClient()` per call.** | ✅ **Resolvido.** Connection pooling com cliente persistente `_get_client()` e `aclose()`. |
| P4 | 🟢 Low | `engine.py` | **RAG search on every message.** | ✅ **Resolvido.** RAG seletivo: queries triviais não disparam busca vetorial. |
| P5 | 🟢 Low | `telegram_bot.py` | **PDF text truncated to 10000 chars.** | ⏳ Agendado para Fase 3 (Chunking multimodal). |

### 5.4 Critical Runtime Bugs (Deep Review Findings)

| ID | Severity | File(s) | Bug | Status & Impact |
|:---|:---------|:--------|:----|:----------------|
| B1 | 🔴 Critical | `engine.py` | **Infinite loop in `get_valid_sequence`.** | ✅ **Resolvido.** Limpeza rigorosa de ToolMessages órfãs sem loop infinito. |
| B2 | 🔴 Critical | `telegram_bot.py` | **`await response.aread()` crashes.** | ✅ **Resolvido.** Utiliza `response.write_to_file()` nativo do OpenAI TTS SDK. |
| B3 | 🟡 High | `engine.py` | **Malformed date timezone append.** | ✅ **Resolvido.** Função `_normalize_ticktick_date` gera ISO compliant. |
| B4 | 🔴 Critical | `obsidian.py` | **Path traversal vulnerability.** | ✅ **Resolvido.** Validação `_safe_resolve` bloqueia qualquer tentativa fora do vault. |
| B5 | 🟡 High | `reminder_worker.py` | **Infinite reminder loop.** | ✅ **Resolvido.** Fallback de texto puro e marcação garantida de lembrete concluído. |
| B6 | 🟡 High | `telegram_bot.py` | **Telegram 4096 char limit not handled.** | ✅ **Resolvido.** Divisão inteligente em chunks respeitando quebras de linha. |
| B7 | 🟡 Medium | `engine.py` | **Router creates new `ChatOpenAI` instance every turn.** | ✅ **Resolvido.** Reutilização da instância singleton de `router_model`. |
| B8 | 🟡 Medium | `engine.py` | **RAG context truncated to 200 chars.** | ✅ **Resolvido.** Contexto expandido para 1000 chars por documento relevante. |
| B9 | 🟢 Low | `engine.py` | **Date filter uses string `in` operator.** | ✅ **Resolvido.** Normalização de datas e comparadores ISO robustos. |
| B10 | 🔴 Critical | `domain/temporal.py`, `database.py` | **Railway UTC time shift (+3h) & Relative Date Distortion.** Em contêineres Linux/Railway, timestamps e saudações usavam UTC, atrasando/adiantando a percepção de tempo em 3h e desorientando a IA em relação ao dia civil e horário do Erik. | ✅ **Resolvido.** Criado módulo centralizado `src/domain/temporal.py` com `ZoneInfo("America/Sao_Paulo")`, resolução temporal estrita (`resolve_temporal_context`), conversão garantida de UTC para local em reminders do Postgres e inclusão de `tzdata==2026.2`. |
| B11 | 🔴 Critical | `engine.py` | **OpenAI Reasoning Effort 400 with Function Tools.** Erro 400 ao invocar `gpt-5.6-luna` com ferramentas no endpoint `/v1/chat/completions`: `Function tools with reasoning_effort are not supported...`. | ✅ **Resolvido.** Injeção automática de `reasoning_effort="none"` para modelos de raciocínio no endpoint de chat e mecanismo de fallback adaptativo em tempo de execução no `MaeveEngine`. |
| B12 | 🔴 Critical | `engine.py` | **Anthropic `temperature` Deprecation 400 Error.** A API da Anthropic depreciou formalmente `temperature` na rota `/v1/messages` para novos modelos (Claude Sonnet 5, etc.), rejeitando com erro 400 qualquer requisição com `temperature=0`. | ✅ **Resolvido.** Configurado `temperature=None` na factory `create_chat_model` para o SDK omitir o parâmetro do payload HTTP, acrescido de recuperação adaptativa caso qualquer restrição residual de amostragem ocorra. |
| B13 | 🔴 Critical | `services/telegram_bot.py`, `agent/engine.py` | **Anthropic Response Ingestion & astream_events v1 Deprecation (Empty Telegram Response).** No streaming de eventos com Anthropic (`ChatAnthropic`), a ausência de `streaming=True` e a estrutura de `ChatResult` do `astream_events(v1)` faziam com que o evento `on_chat_model_end` não tivesse `.content`, deixando a resposta vazia ("Não consegui gerar uma resposta.") e disparando `LangChainDeprecationWarning`. Além disso, listas de content blocks do Anthropic podiam causar falhas de tipo de string. | ✅ **Resolvido.** Migrado para `astream_events(version="v2")`, habilitado `streaming=True` no `ChatAnthropic`, implementada a função resiliente `extract_text_from_message` e adicionado triplo fallback de captura (stream chunk, model end e chain end). |
| B14 | 🟡 High | `services/database.py` | **Dangling AsyncConnectionPool Tasks & Supabase SNI Break.** Falhas no setup do checkpointer descartavam `self.pool = None` sem `await pool.close()`, gerando `asyncio - ERROR - Task was destroyed but it is pending!` pelos workers do `psycopg_pool` ao rodar o garbage collector. Além disso, substituir hostname por IPv4 quebrava o roteamento SNI e validação SSL da Supabase. | ✅ **Resolvido.** Conexão direta via parâmetro `hostaddr` preservando o hostname para SNI/SSL, e encerramento garantido (`await pool.close()`) no bloco `except` e no método `close()` do `DatabaseService`. |

### 5.5 Testing & Observability Gaps

| ID | Severity | Issue | Status & Fix |
|:---|:---------|:------|:-------------|
| T1 | 🟡 Medium | **Zero test coverage.** | ✅ **Resolvido.** Suíte de testes de regressão criada em `src/test/test_bugfixes_regression.py`. |
| T2 | 🟡 Medium | **No structured logging.** | ⏳ Padronização com JSON formatter prevista na Fase 3. |
| T3 | 🟢 Low | **No health check endpoint.** | ✅ **Resolvido.** Endpoint `GET /health` ativo reportando DB pool e status do agente. |

---

## 6. Roadmap de Desenvolvimento

### Fase 1: MVP Local (Concluído ✅)
*   **[✅] Infraestrutura Docker:** Cluster local com `agent-app` (Python/FastAPI) e `local-vector-db` (Qdrant).
*   **[✅] Engine do Agente:** Orquestração com **LangGraph** permitindo Tool Calling e memória de curto prazo.
*   **[✅] Integração Notion (Read):** Sincronização de páginas e bancos de dados para o Qdrant.
*   **[✅] Integração TickTick (Operational):** Implementação de OAuth2 e ferramentas para criar/listar tarefas.
*   **[✅] Semantic Memory (RAG):** Busca vetorial no Qdrant integrada ao prompt de sistema da Maeve.

### Fase 2: Interface, Persistência & Multimodalidade (Concluída ✅)
*   **[✅] Persistência Robusta:** Threads, checkpoints e lembretes integrados ao Supabase com resiliência a quedas de conexão.
*   **[✅] Interface Multimodal:** Suporte total a voz (Whisper) e áudio (TTS) com vozes personalizáveis via `/voz`.
*   **[✅] Otimização TickTick:** Edição em lote (Batch-only), Time Blocking inteligente e mentalidade Agile (Épicos/Stories).
*   **[✅] Pesquisa Web Integrada:** Motores de busca rápida e Deep Research (Tavily) com feedback visual no Telegram.
*   **[✅] Deploy Cloud:** Infraestrutura pronta para Railway/Render com segurança via API Key e SSH dinâmico.

### Fase 3: Inteligência Avançada & Otimização (Concluída ✅)
*   **[✅] Roteamento de Modelos & Multi-Provider:** Arquitetura Híbrida com Factory polimórfica (`create_chat_model` em `engine.py`). Roteamento dinâmico combinando OpenAI (GPT-5.6 Luna como modelo Fast/Router com `reasoning_effort="none"` para tools) e Anthropic (Claude Sonnet como modelo Smart/Deep Reasoning para Obsidian e RAG com `temperature=None`), com fallback gracioso e zero acoplamento.
*   **[✅] Infraestrutura Obsidian (Cloud):** Railway Volumes para manter o Vault clonado permanentemente. Estratégia de `git init` para compatibilidade com volumes.
*   **[✅] Consciência Temporal Estrita:** Módulo dedicado `src/domain/temporal.py` com fuso horário oficial de Brasília (`America/Sao_Paulo`, UTC-3), eliminando distorções de timezone em contêineres Railway/Linux e normalizando agendamento de tarefas e lembretes.
*   **[✅] Refactoring Estrutural:** Clean Hexagonal Architecture implementada. Camada de Domínio Pura (`src/domain/`), Adaptadores Inbound (`src/agent/tools/`), REST modular (`src/api/routes/`), e eliminação do God Module (`engine.py`).
*   **[✅] Naturalidade & Persona Dinâmica Assimétrica:**
    *   **Tier Fast (GPT-5.6 Luna):** Condicionado com 3 Few-Shot Examples (criação de task com time-blocking, consulta de backlog, suporte técnico Python), respostas ágeis de 2 a 5 linhas, gírias dev brasileiras autênticas.
    *   **Tier Smart (Claude Sonnet):** Ancorado nos 4 Pilares Comportamentais (Curva Circadiana de Energia [madrugada, manhã, tarde, noite], Anti-Sycophancy & Devil's Advocate de Staff Engineer contra sobreengenharia, Continuidade Episódica/Amizade Real e Curadoria Ativa do Segundo Cérebro no Obsidian via método CODE).
    *   **Despacho Dinâmico:** Função `get_system_prompt(tier=...)` acoplada ao router do LangGraph.
*   **[ ] Visão Computacional:** Processamento de imagens e fotos via Telegram para extração de insights no Obsidian.
*   **[ ] Dashboard Web:** Interface administrativa para monitorar sincronização e logs do agente.

### Fase 4: MCP Server — Maeve como Camada de Contexto para Antigravity 🚀🚀

> **Objetivo Estratégico:** Transformar a Maeve de um agente conversacional isolado em uma **camada de contexto universal** que qualquer LLM/agent pode consumir via MCP. O primeiro consumidor é o **Antigravity (agy CLI)**, utilizado no dia a dia de trabalho do Erik.

#### 4.1 Visão: O Paradigma "Context-as-a-Service"

```text
┌─────────────────────────────────────────────────────────────────┐
│                    ERIK'S WORKSPACE                              │
│                                                                 │
│  ┌──────────────────┐          ┌──────────────────────────┐     │
│  │  Antigravity CLI  │  stdio   │  maeve-mcp-server        │     │
│  │  (agy)            │◄───────►│  (FastMCP / Python)       │     │
│  │                   │  MCP     │                          │     │
│  │  ┌─ Gemini ──┐    │         │  ┌── Tools ────────────┐  │     │
│  │  │ Flash/Pro │    │         │  │ memory_search       │  │     │
│  │  │ Claude    │    │         │  │ memory_store        │  │     │
│  │  │ Any Model │    │         │  │ get_personal_context│  │     │
│  │  └───────────┘    │         │  │ list_today_tasks    │  │     │
│  └──────────────────┘          │  │ create_task         │  │     │
│                                │  │ search_knowledge    │  │     │
│                                │  │ get_personality     │  │     │
│                                │  │ log_decision        │  │     │
│                                │  └─────────────────────┘  │     │
│                                │            │              │     │
│                                │            ▼              │     │
│                                │  ┌── Backends ─────────┐  │     │
│                                │  │ Obsidian Vault      │  │     │
│                                │  │ Qdrant (Embeddings) │  │     │
│                                │  │ TickTick API        │  │     │
│                                │  │ Supabase (Memory)   │  │     │
│                                │  └─────────────────────┘  │     │
│                                └──────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

**O insight central:** O Antigravity é extremamente poderoso para coding, mas não tem contexto pessoal do Erik — não sabe suas prioridades, não conhece seus projetos pessoais, não lembra de decisões passadas, não tem personalidade. A Maeve já tem tudo isso. O MCP é a ponte.

**Princípio de design:** O MCP server **NÃO substitui** o Antigravity. Ele **enriquece** qualquer modelo que o Antigravity use (Gemini, Claude, etc.) com:
1. **Memória Semântica** — "O que o Erik já pesquisou/decidiu sobre X?"
2. **Contexto Operacional** — "Quais tarefas ele tem hoje? Qual é a prioridade?"
3. **Personalidade & Tom** — "Como a Maeve falaria isso?" (system prompt injection)
4. **Decision Log** — "Registra que o Erik decidiu usar Approach A sobre B neste projeto."

#### 4.2 Arquitetura Técnica do MCP Server

**Transporte:** `stdio` (padrão para Antigravity local).
**Framework:** `FastMCP` (Python SDK v2+).
**Localização:** `src/mcp/server.py` (novo módulo no monorepo da Maeve).

**Dependências dos backends:**
- O MCP server reutiliza os serviços existentes (`ObsidianService`, `VectorDBService`, `TickTickService`, `DatabaseService`).
- Para funcionar via stdio sem o servidor FastAPI rodando, os serviços precisam ser inicializáveis de forma independente (reforça o fix A2 — singleton registry).

#### 4.3 Tools Expostas via MCP

| Tool Name | Descrição | Backend | Prioridade |
|:----------|:----------|:--------|:-----------|
| `memory_search` | Busca semântica no Segundo Cérebro do Erik. Recebe uma query em linguagem natural e retorna notas/contextos relevantes do Obsidian (via Qdrant). | VectorDBService + ObsidianService | P0 |
| `memory_store` | Salva um novo insight, decisão ou aprendizado no Obsidian. O agente pode chamar isso quando o Erik resolve um bug complexo ou toma uma decisão arquitetural. | ObsidianService | P0 |
| `get_personal_context` | Retorna um bloco de contexto pessoal formatado: data/hora, tarefas do dia, humor recente, projetos ativos. Ideal para injetar no system prompt. | TickTickService + DatabaseService | P0 |
| `list_today_tasks` | Lista as tarefas pendentes do Erik para hoje no TickTick, com prioridade e status. | TickTickService | P1 |
| `create_task` | Cria uma tarefa no TickTick a partir do contexto de trabalho (ex: "Criar issue para refatorar módulo X"). | TickTickService | P1 |
| `search_knowledge` | Busca full-text nas notas do Obsidian (sem embeddings, mais rápido para buscas exatas). | ObsidianService | P1 |
| `get_maeve_personality` | Retorna o system prompt / persona da Maeve para que o modelo do Antigravity possa adotar o mesmo tom e estilo. | Prompts module | P2 |
| `log_decision` | Registra uma decisão técnica ou pessoal no Obsidian com timestamp, contexto e rationale. Cria automaticamente uma nota em `Decisões/`. | ObsidianService | P2 |
| `get_project_notes` | Retorna as notas do Obsidian relacionadas a um projeto específico (por pasta ou tag). | ObsidianService | P2 |
| `set_reminder` | Agenda um lembrete que será enviado via Telegram. | DatabaseService | P2 |

#### 4.4 Resources Expostos via MCP

| Resource URI | Descrição | Tipo |
|:-------------|:----------|:-----|
| `maeve://personality/system-prompt` | System prompt completo da Maeve com persona, regras comportamentais e contexto temporal. | text |
| `maeve://context/daily-briefing` | Briefing do dia: data, tarefas, lembretes, última atividade. | text |
| `maeve://knowledge/{path}` | Conteúdo de uma nota específica do Obsidian pelo caminho relativo. | text |

#### 4.5 Implementação: Estrutura de Arquivos

```text
src/
├── mcp/
│   ├── __init__.py
│   ├── server.py          # FastMCP server definition + tool registrations
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── memory.py      # memory_search, memory_store, search_knowledge
│   │   ├── tasks.py       # list_today_tasks, create_task
│   │   ├── context.py     # get_personal_context, get_maeve_personality
│   │   └── decisions.py   # log_decision, get_project_notes
│   └── resources/
│       ├── __init__.py
│       └── providers.py   # Resource providers for personality, briefing, notes
├── services/
│   ├── registry.py        # NEW: Singleton service registry (fixes A2)
│   └── ... (existing services)
```

#### 4.6 Configuração no Antigravity

Arquivo: `~/.gemini/config/mcp_config.json`

```json
{
  "mcpServers": {
    "maeve": {
      "command": "python",
      "args": ["-m", "src.mcp.server"],
      "env": {
        "OBSIDIAN_VAULT_PATH": "E:/mtserik/Documents/ObsidianVault",
        "QDRANT_URL": "http://localhost:6333",
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "TICKTICK_ACCESS_TOKEN": "${TICKTICK_ACCESS_TOKEN}",
        "SUPABASE_DB_URL": "${SUPABASE_DB_URL}"
      }
    }
  }
}
```

**Notas de configuração:**
- O `command` aponta para o Python do venv do projeto Maeve, ou usa `uv run` se gerenciado por uv.
- As variáveis `${...}` serão resolvidas pelo ambiente do shell do Erik.
- O server roda como processo stdio — o Antigravity spawna ele automaticamente.

#### 4.7 Exemplo de Fluxo de Uso

**Cenário:** Erik está debugando um erro de serialização no trabalho.

1. Erik digita no Antigravity: *"Maeve, já enfrentei esse tipo de erro antes?"*
2. O modelo do AGY detecta a tool `memory_search` e chama:
   ```json
   {"name": "memory_search", "arguments": {"query": "erro serialização JSON Python"}}
   ```
3. O MCP server executa uma busca vetorial no Qdrant → encontra uma nota do Obsidian: *"Bug Fix: Serialização de datetime em FastAPI (2026-07-15)"*.
4. O modelo recebe o contexto e responde: *"Sim! Em julho você resolveu um problema parecido no projeto FastAPI. A solução foi usar um custom JSONEncoder..."*

**Cenário:** Erik termina uma refatoração importante.

1. Erik digita: *"Registra que decidi usar o padrão Repository ao invés de Active Record neste projeto."*
2. O AGY chama `log_decision`:
   ```json
   {"name": "log_decision", "arguments": {
     "title": "Repository Pattern vs Active Record",
     "context": "Projeto XYZ - Refatoração da camada de dados",
     "decision": "Repository Pattern",
     "rationale": "Melhor testabilidade e separação de concerns"
   }}
   ```
3. A Maeve cria `Decisões/2026-09-03_Repository-Pattern-vs-Active-Record.md` no Obsidian com frontmatter YAML e faz git push.

#### 4.8 Plano de Implementação (Sprints)

**Sprint 1: Fundação (Pré-requisitos)** — Estimativa: 2-3 dias
- [ ] Criar `src/services/registry.py` com singleton registry (fix A2)
- [ ] Eliminar circular imports no `telegram_bot.py` (fix A3)
- [ ] Extrair tools de `engine.py` para módulos separados (fix A1)
- [ ] Adicionar `fastmcp` ao `requirements.txt`

**Sprint 2: MCP Server Core (P0 Tools)** — Estimativa: 2-3 dias
- [ ] Criar `src/mcp/server.py` com FastMCP + stdio transport
- [ ] Implementar `memory_search` (wrapper do `VectorDBService.search_context`)
- [ ] Implementar `memory_store` (wrapper do `ObsidianService.write_note`)
- [ ] Implementar `get_personal_context` (agregação de TickTick + datetime + mood)
- [ ] Testar com `mcp dev src/mcp/server.py`

**Sprint 3: Integração AGY + Tools P1** — Estimativa: 1-2 dias
- [ ] Configurar `~/.gemini/config/mcp_config.json` apontando para o server
- [ ] Implementar `list_today_tasks` e `create_task`
- [ ] Implementar `search_knowledge` (full-text search no Obsidian)
- [ ] Validar end-to-end: AGY → MCP → Qdrant/TickTick → resposta

**Sprint 4: Resources + Tools P2** — Estimativa: 2 dias
- [ ] Implementar resource providers (personality, briefing, knowledge)
- [ ] Implementar `log_decision` e `get_project_notes`
- [ ] Implementar `get_maeve_personality` e `set_reminder`
- [ ] Documentar usage patterns no README

**Sprint 5: Polimento** — Estimativa: 1-2 dias
- [ ] Structured logging no MCP server (stderr only!)
- [ ] Error handling robusto (timeouts, fallbacks)
- [ ] Testes unitários para cada tool
- [ ] Performance profiling (latência por tool call)

---

## 7. Melhorias Prioritárias (Quick Wins)

Independente do MCP, estas melhorias devem ser aplicadas para a saúde geral do projeto:

### 7.1 Imediatas (Bloqueiam o MCP)
1. **Service Registry** — Centralizar instâncias dos serviços. Sem isso, o MCP server não pode reutilizar serviços sem duplicação.
2. **Async subprocess** — `obsidian.py` usa `subprocess.run()` em métodos `async`. Trocar para `asyncio.create_subprocess_exec()`.
3. **Async embeddings** — `vector_db.py` L46 usa `embed_documents()` sync. Trocar para `aembed_documents()`.

### 7.2 Importantes (Melhoram qualidade geral)
4. **Model names em env vars** — Tornar `gpt-4o-mini` e `gpt-4o` configuráveis.
5. **Lifespan migration** — Trocar `@app.on_event` por `@app.lifespan`.
6. **Pin dependencies** — Adicionar versões no `requirements.txt`.
7. **Remove dead code** — `notion.py`, `chat.py`, `requests` dependency.
8. **Health endpoint** — `GET /health` com status de DB e Qdrant.

### 7.3 Desejáveis (Qualidade de vida)
9. **Structured logging** — Substituir `print()` por `logging` com JSON formatter.
10. **Stable vector IDs** — Usar `uuid5` ao invés de `hash()` para point IDs no Qdrant.
11. **httpx session reuse** — Criar client persistente no `TickTickService`.
12. **Router heuristics** — Pre-filter antes do LLM call para mensagens triviais.

---

## 8. Onboarding Instructions for AI Assistants

When initializing a new session or entering Agent Mode inside this repository, your first task is to read this file (AGENTS.md) along with `docker-compose.yml` to align your internal context window.

**Context priorities:**
1. Read Section 5 (Code Quality Audit) to understand current tech debt.
2. Read Section 6.4 (MCP Server Plan) to understand the next major feature.
3. Read Section 7 (Quick Wins) to know what refactoring is needed first.

Greet Erik, acknowledge the current structural status of the project, and guide him based on where we are in the roadmap. The immediate priority is **Fase 4: MCP Server** with the prerequisite refactoring from Section 7.1.

---

## 9. Histórico de Sprints & Entregas Recentes (Sprint Ledger)

### 9.1 Sprint 10: Modelos de Fronteira, Fuso Horário de Brasília & Persona Assimétrica (2026-09-04)

> **Objetivo:** Atualizar os modelos neurais da Maeve para máxima relação custo-benefício, estabilizar o fuso horário no Railway, resolver incompatibilidades de runtime dos novos modelos (OpenAI & Anthropic) e implementar a arquitetura de Persona Dinâmica Assimétrica.

#### 1. Pesquisa & Benchmarking de Modelos
- **Fast / Router Model:** Adoção do **GPT-5.6 Luna** da OpenAI (substituindo GPT-4o-mini). Oferece latência de resposta inferior a 600ms, raciocínio nativo para classificação de intenções e custo de apenas ~$0,15 / $0,60 por milhão de tokens, gerando custo mensal estimado < $1,00 para o volume da Maeve.
- **Smart / Deep Reasoning Model:** Adoção do **Claude Sonnet** da Anthropic (substituindo GPT-4o). Oferece qualidade superior de raciocínio para sínteses do Segundo Cérebro (Obsidian), decomposição de tarefas complexas e anti-sycophancy.
- **Análise de Custos Railway:** Avaliado e aprovado o plano de $5/mês do Railway, garantindo uptime 24/7 do container sem risco de esgotamento prematuro de créditos.

#### 2. Consciência Temporal Estrita (Fuso Horário de Brasília)
- **Problema:** Em produção no Railway (ambiente Linux baseado em UTC), a Maeve calculava horários com desvio de +3h e se perdia em termos relativos ("hoje", "amanhã", "às 15h").
- **Solução Técnica:**
  - Criação do módulo de domínio `src/domain/temporal.py` utilizando `zoneinfo.ZoneInfo("America/Sao_Paulo")`.
  - Funções de domínio puro: `get_local_now()`, `resolve_temporal_context()` e `to_local_datetime()`.
  - Normalização no serviço de banco de dados (`src/services/database.py`) para converter timestamps UTC do PostgreSQL para horário local de Brasília ao carregar lembretes.
  - Pinagem da dependência `tzdata==2026.2` no `requirements.txt`.

#### 3. Estabilização de Runtime de Provedores (Bugfixes B11 & B12)
- **OpenAI Reasoning Effort com Function Calling (B11):** No endpoint `/v1/chat/completions`, os novos modelos da OpenAI (GPT-5.x, Luna, Terra, Sol) exigem explicitamente `reasoning_effort="none"` quando ferramentas/tools estão ativas. Implementada configuração automática na factory `create_chat_model` e fallback adaptativo em tempo de execução no `MaeveEngine`.
- **Anthropic Temperature Deprecation (B12):** Modelos Claude recentes (Sonnet 5) depreciaram o parâmetro de amostragem `temperature` na rota `/v1/messages`. Qualquer valor enviado (inclusive `0.0`) gerava erro 400. Configurado `temperature=None` na factory `create_chat_model` para suprimir a chave do payload JSON, garantindo conformidade total com a API.

#### 4. Arquitetura de Persona Dinâmica Assimétrica
- **Motivação:** Um prompt monolítico degradava modelos rápidos de execução (gerando respostas prolixas ou alucinações de tom) e subaproveitava o potencial analítico de modelos de fronteira.
- **Implementação:**
  - `FAST_PROMPT_TEMPLATE` (Luna): Condicionamento por Few-Shot Learning (3 exemplos reais: agendamento com time-blocking, backlog diário, suporte técnico direto), respostas ultraconcisas (2 a 5 linhas), gírias dev brasileiras autênticas.
  - `SMART_PROMPT_TEMPLATE` (Sonnet): Ancorado em 4 Pilares Comportamentais:
    1. *Ritmo Circadiano Dinâmico:* Tom e energia modulados pela hora do dia (madrugada cúmplice e enxuta, manhã estratégica e Big Rock, tarde de foco/tração, noite de wrap-up e anti-burnout).
    2. *Anti-Sycophancy & Devil's Advocate:* Postura de Staff Engineer questionando sobreengenharia (overengineering), gambiarras perigosas e backlogs irreais.
    3. *Continuidade Episódica & Amizade Real:* Comemoração de marcos reais e empatia contextual sob estresse agudo.
    4. *Curadoria Ativa do Segundo Cérebro:* Método CODE no Obsidian com captura de insights e conexão semântica.
  - Função despachante `get_system_prompt(tier=...)` em `src/agent/prompts.py` integrada ao loop de inferência do LangGraph.
  - Mandato estrito de formatação para Telegram: proibição de hashtags `#` e `##`, uso exclusivo de negrito em linha isolada para títulos.

#### 5. Qualidade, Testes & CI/CD
- 100% de aprovação na suíte de testes unitários e de regressão (`test_domain_services.py` e `test_bugfixes_regression.py`).
- Commits `b9ac39f`, `a3e56fb` e `61b7c03` integrados na branch `main` e deployados com sucesso no Railway.