# Project Maeve: Context-Aware Knowledge & Task Orchestrator

Maeve é um assistente de IA multimodal de alta performance, projetado para atuar como um **Segundo Cérebro proativo** e co-piloto de desenvolvimento. Ela integra gestão de conhecimento (Obsidian), produtividade (TickTick), pesquisa em tempo real (Tavily) e comunicação multimodal (Telegram).

## 🚀 Funcionalidades Principais (v0.3.0)

- **🧠 Segundo Cérebro (Obsidian):** Sincronização bidirecional via Git, indexação vetorial (RAG) e criação proativa de notas.
- **📅 Gestão Agile (TickTick):** Planejamento de agenda com estimativa de esforço, Épicos, Tasks e Time Blocking inteligente.
- **🎙️ Multimodalidade:** Suporte a mensagens de voz (Whisper) e respostas em áudio (OpenAI TTS) com vozes personalizáveis.
- **🌐 Pesquisa Web:** Busca rápida e "Deep Research" usando a API Tavily para informações sempre atualizadas.
- **🔔 Lembretes Proativos:** Sistema de notificações push via Telegram com persistência no Supabase.
- **🛡️ Segurança de Produção:** Endpoints protegidos por API Key (X-API-Key) e SSH dinâmico para deploy cloud.

## 🛠️ Stack Técnica

- **Linguagem:** Python 3.11
- **Framework Web:** FastAPI
- **Orquestração de IA:** LangGraph / LangChain
- **LLM:** OpenAI (GPT-4o-mini / Whisper / TTS)
- **Banco Vetorial:** Qdrant Cloud
- **Persistência Relacional:** Supabase (PostgreSQL)
- **Infraestrutura:** Docker & Railway

## 📦 Como Rodar Localmente

1.  Clone o repositório.
2.  Configure o arquivo `.env` com base no `.env.example`.
3.  Certifique-se de ter suas chaves SSH configuradas para o Obsidian.
4.  Execute o cluster:
    ```bash
    docker-compose up --build
    ```

## ☁️ Deploy Cloud (Railway)

Este projeto está otimizado para o Railway. Basta conectar seu repositório GitHub e configurar as variáveis de ambiente. O deploy é disparado automaticamente a cada push na branch `main`.
