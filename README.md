# Containerized LLM Agent: Context-Aware Knowledge & Task Orchestrator

An autonomous, cross-platform personal assistant designed to bridge semantic knowledge management with operational workflows. This system integrates a **Model Context Protocol (MCP)** or API-driven framework to interact dynamically with a user's task manager (**TickTick**) and custom knowledge bases (**Notion/Obsidian Second Brain**), using an LLM brain orchestrated through **LangGraph**.

The entire architecture is containerized using **Docker** to ensure strict Dev-Prod parity, allowing a seamless transition from a local development MVP to a fully scalable cloud environment.

---

## 🏗️ Core Architecture

The system utilizes a decoupled, event-driven design split into isolated services:

*   **App Engine (FastAPI + LangGraph):** Handles the core state machine, execution of tools, and semantic intent routing using advanced LLMs (e.g., Claude 3.5 Sonnet / GPT-4o-mini).
*   **Vector Memory (Qdrant / pgvector):** A highly optimized vector database storing mathematical embeddings of private notes to support Retrieval-Augmented Generation (RAG).
*   **Bi-directional Ingestion:** Live API workers that actively read knowledge streams and update contextual records autonomously.

---

## 🛠️ Tech Stack & Prerequisites

*   **Language:** Python 3.11+
*   **Frameworks:** LangGraph, LangChain, FastAPI
*   **Database:** Qdrant (Local MVP) / Supabase PostgreSQL (Production Cloud)
*   **Containerization:** Docker & Docker Compose
*   **External Integrations:** Notion API, TickTick API/MCP, OpenAI / Anthropic APIs

---

## 🚀 Local MVP Setup

### 1. Clone the Repository
```bash
git clone [https://github.com/your-username/containerized-llm-agent.git](https://github.com/your-username/containerized-llm-agent.git)
cd containerized-llm-agent
```
### 2. Configure Environment Variables
This project strictly enforces credential isolation. Never commit raw API keys to version control.

Duplicate the template environment file and populate your credentials privately:

```bash
cp .env.example .env
```

### 3. Spin Up the Environment
Orchestrate and start the containerized app and local vector database with a single command:
```bash
docker-compose up --build
```
The FastAPI application wrapper will expose local endpoints at http://localhost:8000.

---

## 🔒 Security & Data Privacy
To protect proprietary data, personal routines, and corporate coffee industry insights:

The .env file is explicitly blacklisted in .gitignore.

Local data volumes mapped to qdrant_storage reside outside the version-controlled directory.

Production cloud endpoints require signed JWT cryptographic authorization headers to accept remote payloads.

---

## 📜 License
This project is licensed under the MIT License - see the LICENSE file for details.
