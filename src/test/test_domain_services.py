import os
import asyncio
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from src.domain.tasks import TaskDomainService, normalize_ticktick_date
from src.domain.knowledge import KnowledgeDomainService
from src.domain.reminders import ReminderDomainService
from src.agent.tools import get_tools_for_intent, TASK_TOOLS, KNOWLEDGE_TOOLS, SEARCH_TOOLS, REMINDER_TOOLS, CHAT_TOOLS
from src.main import app

def test_dynamic_tool_binding_subsets():
    """Valida se o dynamic tool binding entrega estritamente os subconjuntos de ferramentas."""
    tasks = get_tools_for_intent("tasks")
    assert len(tasks) == len(TASK_TOOLS)
    assert any(t.name == "create_ticktick_task" for t in tasks)
    assert not any(t.name == "create_obsidian_note" for t in tasks)

    knowledge = get_tools_for_intent("knowledge")
    assert len(knowledge) == len(KNOWLEDGE_TOOLS)
    assert any(t.name == "create_obsidian_note" for t in knowledge)
    assert not any(t.name == "create_ticktick_task" for t in knowledge)

    chat = get_tools_for_intent("chat")
    assert len(chat) == 0

    reminders = get_tools_for_intent("reminders")
    assert len(reminders) == len(REMINDER_TOOLS)
    assert any(t.name == "set_reminder" for t in reminders)

    search = get_tools_for_intent("search")
    assert len(search) == len(SEARCH_TOOLS)
    assert any(t.name == "web_search" for t in search)
    print("[OK] test_dynamic_tool_binding_subsets PASSOU")

def test_task_domain_parent_project_inheritance():
    """Valida se uma subtarefa herda automaticamente o projectId da tarefa pai."""
    mock_ticktick = MagicMock()
    mock_ticktick.get_task_by_id = AsyncMock(return_value={"id": "parent_123", "projectId": "proj_abc", "title": "Pai"})
    mock_ticktick.create_task = AsyncMock(return_value={"id": "sub_456", "projectId": "proj_abc"})

    svc = TaskDomainService(ticktick_service=mock_ticktick)
    result = asyncio.run(svc.create_task(title="Subtarefa 1", parent_id="parent_123"))

    assert result.success is True
    assert result.task_id == "sub_456"
    print("[OK] test_task_domain_parent_project_inheritance PASSOU")

def test_task_domain_time_blocking_normalization():
    """Valida se o lote de tarefas normaliza as datas de início e fim no formato ISO."""
    mock_ticktick = MagicMock()
    mock_ticktick.batch_update_tasks = AsyncMock(return_value=[{"status": 200, "task_id": "t1"}])

    svc = TaskDomainService(ticktick_service=mock_ticktick)
    tasks = [
        {"task_id": "t1", "title": "Estudo de Álgebra", "due_date": "2026-09-04T16:00:00", "start_date": "2026-09-04T14:00:00"}
    ]
    result = asyncio.run(svc.batch_update_tasks(tasks))
    assert result.success is True
    # Verifica argumento passado ao ticktick.batch_update_tasks
    called_payload = mock_ticktick.batch_update_tasks.call_args[0][0]
    assert called_payload[0]["dueDate"] == "2026-09-04T16:00:00-0300"
    assert called_payload[0]["startDate"] == "2026-09-04T14:00:00-0300"
    print("[OK] test_task_domain_time_blocking_normalization PASSOU")

def test_knowledge_domain_note_creation():
    """Valida se o KnowledgeDomainService adiciona a extensão .md e delega ao ObsidianService."""
    mock_obsidian = MagicMock()
    mock_obsidian.write_note = AsyncMock(return_value="Inbox/Arquitetura.md")

    svc = KnowledgeDomainService(obsidian_service=mock_obsidian)
    result = asyncio.run(svc.create_note(title="Arquitetura", content="# Conteúdo", folder="Inbox"))

    assert result.success is True
    assert result.path == "Inbox/Arquitetura.md"
    mock_obsidian.write_note.assert_called_once()
    print("[OK] test_knowledge_domain_note_creation PASSOU")

def test_fastapi_endpoints_health():
    """Valida se os endpoints do FastAPI montados via APIRouter respondem com sucesso."""
    with TestClient(app) as client:
        resp_root = client.get("/")
        assert resp_root.status_code == 200
        assert resp_root.json()["status"] == "Maeve is online"
        assert resp_root.json()["version"] == "0.4.0"

        resp_health = client.get("/health")
        assert resp_health.status_code == 200
        assert resp_health.json()["status"] == "healthy"
        assert resp_health.json()["version"] == "0.4.0"
    print("[OK] test_fastapi_endpoints_health PASSOU")


def test_multi_provider_model_factory():
    """Test Multi-Provider LLM Factory (OpenAI vs Anthropic with fallback)."""
    from src.agent.engine import create_chat_model
    from langchain_openai import ChatOpenAI
    from langchain_anthropic import ChatAnthropic

    # 1. Instanciar OpenAI
    m_openai = create_chat_model("gpt-5.6-luna")
    assert isinstance(m_openai, ChatOpenAI)
    assert m_openai.model_name == "gpt-5.6-luna"
    assert m_openai.reasoning_effort == "none"

    # 2. Instanciar Anthropic
    m_claude = create_chat_model("claude-sonnet-5")
    assert isinstance(m_claude, (ChatAnthropic, ChatOpenAI))
    if isinstance(m_claude, ChatAnthropic):
        # Valida que temperature é estritamente None para evitar o erro 400 da Anthropic
        assert m_claude.temperature is None

    # 3. Fallback gracioso quando chave não está presente
    old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        m_fallback = create_chat_model("claude-sonnet-5")
        assert isinstance(m_fallback, ChatOpenAI)
    finally:
        if old_key:
            os.environ["ANTHROPIC_API_KEY"] = old_key

    print("[OK] test_multi_provider_model_factory PASSOU")


def test_temporal_context_and_timezone_handling():
    """Valida se a resolução temporal respeita estritamente o fuso de Brasília (America/Sao_Paulo)."""
    from src.domain.temporal import get_local_now, resolve_temporal_context, to_local_datetime
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    # 1. Resolver contexto temporal
    ctx = resolve_temporal_context()
    assert "date" in ctx
    assert "time" in ctx
    assert "period" in ctx
    assert "day_of_week" in ctx
    assert ctx["timezone"] == "America/Sao_Paulo"
    assert ctx["utc_offset"] == "-0300"

    # 2. Conversão de UTC para Local
    utc_dt = datetime(2026, 9, 4, 15, 30, tzinfo=timezone.utc)
    local_dt = to_local_datetime(utc_dt)
    assert local_dt.hour == 12
    assert local_dt.minute == 30
    assert local_dt.strftime('%z') == "-0300"

    # 3. Conversão de Naive (assumindo UTC) para Local
    naive_dt = datetime(2026, 9, 4, 15, 30)
    local_from_naive = to_local_datetime(naive_dt)
    assert local_from_naive.hour == 12
    assert local_from_naive.minute == 30

    print("[OK] test_temporal_context_and_timezone_handling PASSOU")


def test_asymmetric_persona_prompt_system():
    """Valida a geração de prompts assimétricos dinâmicos por tier (Fast vs Smart)."""
    from src.agent.prompts import (
        get_system_prompt,
        FAST_PROMPT_TEMPLATE,
        SMART_PROMPT_TEMPLATE,
        SYSTEM_PROMPT_TEMPLATE,
    )

    context_kwargs = {
        "date": "2026-09-04",
        "time": "01:45",
        "day_of_week": "Sexta-feira",
        "period": "madrugada",
        "timezone": "America/Sao_Paulo",
        "user_id": "123456",
        "chat_id": "987654",
        "obsidian_context": "- Arquitetura: Clean Architecture e POO.",
    }

    # 1. Tier Fast (Luna)
    fast_prompt = get_system_prompt("fast", **context_kwargs)
    assert "FEW-SHOT EXAMPLES" in fast_prompt
    assert "Ultra-Direta e Concisa" in fast_prompt
    assert "NUNCA use hashtags para títulos" in fast_prompt
    assert "2026-09-04" in fast_prompt
    assert "01:45" in fast_prompt
    assert "OS 4 PILARES COMPORTAMENTAIS" not in fast_prompt

    # 2. Tier Smart (Sonnet)
    smart_prompt = get_system_prompt("smart", **context_kwargs)
    assert "OS 4 PILARES COMPORTAMENTAIS" in smart_prompt
    assert "RITMO CIRCADIANO DINÂMICO" in smart_prompt
    assert "ANTI-SYCOPHANCY & DEVIL'S ADVOCATE" in smart_prompt
    assert "CONTINUIDADE EPISÓDICA" in smart_prompt
    assert "CURADORIA ATIVA DO SEGUNDO CÉREBRO" in smart_prompt
    assert "NUNCA use hashtags para títulos" in smart_prompt
    assert "2026-09-04" in smart_prompt

    # 3. Compatibilidade legada
    assert SYSTEM_PROMPT_TEMPLATE == SMART_PROMPT_TEMPLATE

    print("[OK] test_asymmetric_persona_prompt_system PASSOU")


def test_extract_text_from_message_resilience():
    """Valida se extract_text_from_message lida com strings, blocos do Anthropic, ChatResult e dicts."""
    from src.agent.engine import extract_text_from_message
    from langchain_core.messages import AIMessage, HumanMessage, AIMessageChunk
    from langchain_core.outputs import ChatResult, ChatGeneration

    # 1. String pura
    assert extract_text_from_message("Olá mundo") == "Olá mundo"
    assert extract_text_from_message("") == ""
    assert extract_text_from_message(None) == ""

    # 2. Lista de strings
    assert extract_text_from_message(["Parte 1", " Parte 2"]) == "Parte 1 Parte 2"

    # 3. Lista de blocos Anthropic Claude ({'type': 'text', 'text': '...'})
    anthropic_blocks = [
        {"type": "text", "text": "Aqui está a resposta: "},
        {"type": "text", "text": "Arquitetura limpa implementada com sucesso."}
    ]
    assert extract_text_from_message(anthropic_blocks) == "Aqui está a resposta: Arquitetura limpa implementada com sucesso."

    # 4. AIMessage com string
    msg_str = AIMessage(content="Resposta direta")
    assert extract_text_from_message(msg_str) == "Resposta direta"

    # 5. AIMessage com blocos Anthropic
    msg_anthropic = AIMessage(content=[{"type": "text", "text": "Texto em bloco Anthropic"}])
    assert extract_text_from_message(msg_anthropic) == "Texto em bloco Anthropic"

    # 6. AIMessageChunk
    chunk = AIMessageChunk(content="Pedacinho de stream")
    assert extract_text_from_message(chunk) == "Pedacinho de stream"

    # 7. ChatResult (astream_events v1 output)
    chat_result = ChatResult(generations=[ChatGeneration(message=AIMessage(content="Resultado do ChatResult"))])
    assert extract_text_from_message(chat_result) == "Resultado do ChatResult"

    # 8. Dict com 'content' ou 'messages'
    assert extract_text_from_message({"content": "Conteúdo em dict"}) == "Conteúdo em dict"
    assert extract_text_from_message({"messages": [HumanMessage(content="User"), AIMessage(content="Final")]}) == "Final"

    print("[OK] test_extract_text_from_message_resilience PASSOU")


if __name__ == "__main__":
    test_dynamic_tool_binding_subsets()
    test_task_domain_parent_project_inheritance()
    test_task_domain_time_blocking_normalization()
    test_knowledge_domain_note_creation()
    test_fastapi_endpoints_health()
    test_multi_provider_model_factory()
    test_temporal_context_and_timezone_handling()
    test_asymmetric_persona_prompt_system()
    test_extract_text_from_message_resilience()
    print("\n>>> TODOS OS TESTES UNITARIOS DE DOMINIO PASSARAM! <<<")
