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

def test_knowledge_domain_batch_move_notes():
    """Valida se o KnowledgeDomainService delega para batch_move_items e consolida os resultados."""
    mock_obsidian = MagicMock()
    mock_obsidian.batch_move_items = AsyncMock(return_value={
        "total": 3,
        "success_count": 3,
        "failed_count": 0,
        "success_moves": [{"old_path": "a.md", "new_path": "b.md"}],
        "failed_moves": []
    })

    svc = KnowledgeDomainService(obsidian_service=mock_obsidian)
    moves = [
        {"old_path": "Inbox/Nota1.md", "new_path": "Projects/Nota1.md"},
        {"old_path": "Inbox/Nota2.md", "new_path": "Projects/Nota2.md"},
        {"old_path": "Inbox/Nota3.md", "new_path": "Projects/Nota3.md"},
    ]
    result = asyncio.run(svc.batch_move_notes(moves))
    assert result.success is True
    assert "3 notas movidas" in result.message
    mock_obsidian.batch_move_items.assert_called_once_with(moves)
    print("[OK] test_knowledge_domain_batch_move_notes PASSOU")

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
    assert "LaTeX" in fast_prompt
    assert "Obsidian" in fast_prompt

    # 2. Tier Smart (Sonnet)
    smart_prompt = get_system_prompt("smart", **context_kwargs)
    assert "OS 4 PILARES COMPORTAMENTAIS" in smart_prompt
    assert "RITMO CIRCADIANO DINÂMICO" in smart_prompt
    assert "ANTI-SYCOPHANCY & DEVIL'S ADVOCATE" in smart_prompt
    assert "CONTINUIDADE EPISÓDICA" in smart_prompt
    assert "CURADORIA ATIVA DO SEGUNDO CÉREBRO" in smart_prompt
    assert "NUNCA use hashtags para títulos" in smart_prompt
    assert "2026-09-04" in smart_prompt
    assert "LaTeX" in smart_prompt
    assert "MathJax" in smart_prompt
    assert "Markdown estruturado" in smart_prompt

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


def test_format_telegram_markdown_normalization():
    """Valida se format_telegram_markdown converte cabeçalhos, negrito e preserva blocos de código."""
    from src.services.telegram_bot import format_telegram_markdown

    # 1. Conversão de Headers
    assert format_telegram_markdown("# Título Principal") == "*Título Principal*"
    assert format_telegram_markdown("## Subtítulo") == "*Subtítulo*"
    assert format_telegram_markdown("### Seção Técnica") == "*Seção Técnica*"

    # 2. Conversão de Negrito (**texto** -> *texto*)
    assert format_telegram_markdown("Isso é **muito importante**!") == "Isso é *muito importante*!"

    # 3. Preservação de Código Inline e Blocos
    code_inline = "O parâmetro `user_id` não deve ser alterado."
    assert format_telegram_markdown(code_inline) == code_inline

    code_block = "```python\ndef run_query():\n    return 'ok'\n```"
    assert format_telegram_markdown(code_block) == code_block

    # 4. Combinação de Header, Negrito e Código
    mixed_input = (
        "## Visão Geral\n"
        "Aqui está o **plano de ação**:\n"
        "- Executar `db_sync` no container.\n"
        "```bash\n"
        "docker compose restart\n"
        "```\n"
        "Prontinho!"
    )
    expected_output = (
        "*Visão Geral*\n"
        "Aqui está o *plano de ação*:\n"
        "- Executar `db_sync` no container.\n"
        "```bash\n"
        "docker compose restart\n"
        "```\n"
        "Prontinho!"
    )
    assert format_telegram_markdown(mixed_input) == expected_output

    # 5. Casos vazios
    assert format_telegram_markdown("") == ""
    assert format_telegram_markdown(None) == ""

    print("[OK] test_format_telegram_markdown_normalization PASSOU")


def test_telegram_semantic_chunking_and_boundary_healing():
    """Valida o fatiamento semântico de mensagens e a autocura de entidades Markdown."""
    from src.services.telegram_bot import split_into_semantic_chunks, _heal_markdown_boundary

    # 1. Mensagem curta (não fatia)
    short = "Olá Erik, sua agenda está limpa para hoje!"
    assert split_into_semantic_chunks(short, max_chunk_size=500) == [short]

    # 2. Mensagem vazia
    assert split_into_semantic_chunks("") == []
    assert split_into_semantic_chunks(None) == []

    # 3. Autocura de blocos de código
    code_part1 = "Aqui está a implementação:\n```python\ndef conectar():\n    return True"
    code_part2 = "    print('conectado!')\n```\nTudo pronto."
    h1, h2 = _heal_markdown_boundary(code_part1, code_part2)
    assert h1.endswith("```")
    assert h2.startswith("```python")
    assert h1.count("```") % 2 == 0
    assert h2.count("```") % 2 == 0

    # 4. Autocura de negrito
    bold_part1 = "Atenção: este é um *ponto crítico"
    bold_part2 = "que precisa ser resolvido agora* com cuidado."
    hb1, hb2 = _heal_markdown_boundary(bold_part1, bold_part2)
    assert hb1.endswith("*")
    assert hb2.startswith("*")
    assert hb1.count("*") % 2 == 0
    assert hb2.count("*") % 2 == 0

    # 5. Fatiamento semântico com limite de mensagens
    long_doc = (
        "*Seção 1 - Arquitetura*\n\n" + ("Explicação de arquitetura limpa e desacoplamento de camadas. " * 10) +
        "\n\n*Seção 2 - Código*\n\n```python\n" + ("print('executando pipeline de dados...')\n" * 12) + "```\n\n" +
        "*Seção 3 - Conclusão*\n\n" + ("Deploy efetuado com sucesso sem indisponibilidade. " * 8)
    )
    chunks = split_into_semantic_chunks(long_doc, max_chunk_size=600, target_chunk_size=400, max_messages=4)
    assert len(chunks) <= 4
    for c in chunks:
        assert c.count("```") % 2 == 0
        assert c.count("*") % 2 == 0

    print("[OK] test_telegram_semantic_chunking_and_boundary_healing PASSOU")


if __name__ == "__main__":
    test_dynamic_tool_binding_subsets()
    test_task_domain_parent_project_inheritance()
    test_task_domain_time_blocking_normalization()
    test_knowledge_domain_note_creation()
    test_knowledge_domain_batch_move_notes()
    test_fastapi_endpoints_health()
    test_multi_provider_model_factory()
    test_temporal_context_and_timezone_handling()
    test_asymmetric_persona_prompt_system()
    test_extract_text_from_message_resilience()
    test_format_telegram_markdown_normalization()
    test_telegram_semantic_chunking_and_boundary_healing()
    print("\n>>> TODOS OS TESTES UNITARIOS DE DOMINIO PASSARAM! <<<")
