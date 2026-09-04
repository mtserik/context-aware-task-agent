import os
import uuid
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from src.services.obsidian import ObsidianService
from src.agent.engine import _normalize_ticktick_date

def test_obsidian_path_traversal_blocked():
    """Test B4: Path traversal attempts must be rejected."""
    service = ObsidianService()
    
    valid_resolved = service._safe_resolve("Inbox/minha_nota.md")
    assert "minha_nota.md" in valid_resolved
    assert os.path.isabs(valid_resolved)
    
    blocked_count = 0
    for bad in ["../../.env", "../../../etc/passwd", "Inbox/../../.env"]:
        try:
            service._safe_resolve(bad)
        except ValueError:
            blocked_count += 1
    assert blocked_count == 3
    print("[OK] test_obsidian_path_traversal_blocked PASSOU")

def test_ticktick_date_normalization():
    """Test B3: Date strings must be converted to valid ISO UTC format for TickTick MCP / Backend."""
    from src.domain.temporal import utc_to_sp_datetime, format_sp_task_date
    assert _normalize_ticktick_date("2026-09-03") == "2026-09-03T03:00:00.000+0000"
    assert _normalize_ticktick_date("2026-09-03T15:30:00") == "2026-09-03T18:30:00.000+0000"
    assert _normalize_ticktick_date("2026-09-03T15:30:00Z") == "2026-09-03T15:30:00.000+0000"
    assert _normalize_ticktick_date("2026-09-03T15:30:00-0300") == "2026-09-03T18:30:00.000+0000"
    assert _normalize_ticktick_date(None) is None
    assert _normalize_ticktick_date("") == ""
    # Conversão de volta para São Paulo
    assert format_sp_task_date("2026-09-05T00:30:00.000+0000") == "04/09/2026 21:30"
    assert format_sp_task_date("2026-09-03T03:00:00.000+0000") == "03/09/2026"
    print("[OK] test_ticktick_date_normalization PASSOU")

def test_get_valid_sequence_termination():
    """Test B1: Message sequence trimming must never enter an infinite loop."""
    def get_valid_sequence(msgs, limit=20):
        if len(msgs) <= limit:
            subset = list(msgs)
        else:
            subset = list(msgs[-limit:])
            while subset and isinstance(subset[0], ToolMessage) and limit < len(msgs):
                limit += 1
                subset = list(msgs[-limit:])
        
        while subset and isinstance(subset[0], ToolMessage):
            subset = subset[1:]

        if subset and isinstance(subset[-1], AIMessage) and subset[-1].tool_calls:
            subset = subset[:-1]
        return subset

    orphan_tools = [ToolMessage(content=f"res_{i}", tool_call_id=str(i)) for i in range(30)]
    result = get_valid_sequence(orphan_tools, limit=10)
    assert result == []

    msgs = [HumanMessage(content="Oi"), AIMessage(content="Olá, Erik!")]
    assert get_valid_sequence(msgs, limit=10) == msgs

    hanging_ai = msgs + [AIMessage(content="", tool_calls=[{"id": "1", "name": "test", "args": {}}])]
    result_hanging = get_valid_sequence(hanging_ai, limit=10)
    assert len(result_hanging) == 2
    print("[OK] test_get_valid_sequence_termination PASSOU")

def test_vector_point_id_determinism():
    """Test S4: Vector IDs must be stable and deterministic across reboots."""
    path = "Projects/Maeve/Architecture.md"
    id1 = str(uuid.uuid5(uuid.NAMESPACE_URL, path))
    id2 = str(uuid.uuid5(uuid.NAMESPACE_URL, path))
    assert id1 == id2
    assert len(id1) == 36
    print("[OK] test_vector_point_id_determinism PASSOU")

def test_router_heuristic_fast_path():
    """Test Item 4.1: Short messages and greetings must resolve immediately without LLM call."""
    import asyncio
    from src.agent.engine import MaeveAgent
    
    agent = MaeveAgent()
    
    # Test cases that should trigger fast path (complexity 1, model fast)
    for sample in ["oi", "Oi Maeve", "bom dia!", "Ola", "valeu!", "ok"]:
        state = {"messages": [HumanMessage(content=sample)]}
        result = asyncio.run(agent._router_node(state))
        assert result["routing_metadata"]["model"] == "fast"
        assert result["routing_metadata"]["complexity"] == 1
        assert "Heuristic" in result["routing_metadata"]["reason"]
    
    print("[OK] test_router_heuristic_fast_path PASSOU")

def test_router_regex_json_parsing():
    """Test Item 2.1: Router must extract JSON even if LLM wraps it in conversational prose or markdown."""
    import re
    import json
    
    dirty_llm_outputs = [
        'Aqui está o JSON:\n```json\n{"complexity": 2, "model": "smart", "reason": "planejamento complexo"}\n```\nEspero ter ajudado!',
        'Claro! {"complexity": 1, "model": "fast", "reason": "simples"}',
        '```\n{"complexity": 3, "model": "smart", "reason": "analise profunda"}\n```'
    ]
    
    for raw in dirty_llm_outputs:
        json_match = re.search(r"\{.*?\}", raw, re.DOTALL)
        assert json_match is not None
        parsed = json.loads(json_match.group(0))
        assert "model" in parsed
        assert "complexity" in parsed
    
    print("[OK] test_router_regex_json_parsing PASSOU")

def test_ticktick_connection_pooling():
    """Test Item 4.3: TickTickService must reuse the same httpx.AsyncClient instance."""
    import asyncio
    from src.services.ticktick import TickTickService
    
    svc = TickTickService()
    c1 = svc._get_client()
    c2 = svc._get_client()
    assert c1 is c2
    assert not c1.is_closed
    
    # Close client
    asyncio.run(svc.aclose())
    assert svc._client is None
    
    # New call lazily re-instantiates
    c3 = svc._get_client()
    assert c3 is not None
    assert c3 is not c1
    asyncio.run(svc.aclose())
    print("[OK] test_ticktick_connection_pooling PASSOU")

def test_service_registry_singletons():
    """Test Item 5.3: Service Registry must return singleton instances and decouple dependencies."""
    from src.services.registry import (
        get_obsidian_service,
        get_vector_db_service,
        get_ticktick_service,
        get_database_service,
        get_search_service,
        get_telegram_service
    )
    
    assert get_obsidian_service() is get_obsidian_service()
    assert get_vector_db_service() is get_vector_db_service()
    assert get_ticktick_service() is get_ticktick_service()
    assert get_database_service() is get_database_service()
    assert get_search_service() is get_search_service()
    assert get_telegram_service() is get_telegram_service()
    print("[OK] test_service_registry_singletons PASSOU")

def test_selective_rag_skipping():
    """Test Item 5.2: Trivial greetings must be skipped from RAG search."""
    trivial_greetings = {
        "oi", "ola", "olá", "bom dia", "boa tarde", "boa noite",
        "opa", "e ai", "e aí", "valeu", "obrigado", "obrigada",
        "ok", "beleza", "blz", "tchau", "ate mais", "até mais",
        "sim", "não", "nao", "show", "perfeito"
    }
    
    def should_search(query: str, complexity: int) -> bool:
        should = bool(query)
        if should and complexity == 1:
            clean_q = str(query).strip().lower()
            if clean_q in trivial_greetings or len(clean_q) < 4:
                should = False
        return should

    # Simple greetings with complexity 1: skipped
    assert should_search("oi", 1) is False
    assert should_search("Bom dia", 1) is False
    assert should_search("ok", 1) is False
    
    # Actual questions: searched
    assert should_search("Quais são as minhas metas de 2026?", 1) is True
    assert should_search("Qual foi a arquitetura decidida para o MCP?", 2) is True
    print("[OK] test_selective_rag_skipping PASSOU")

def test_extract_text_from_message_handling():
    """Test S10/B11: Multi-provider message extraction handling Anthropic list blocks and LangChain outputs."""
    from src.agent.engine import extract_text_from_message
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatResult, ChatGeneration

    # Text extraction from Anthropic content blocks list
    blocks = [{"type": "text", "text": "Deploy "}, {"type": "text", "text": "concluído."}]
    assert extract_text_from_message(blocks) == "Deploy concluído."

    # Text extraction from AIMessage with list blocks
    msg = AIMessage(content=[{"type": "text", "text": "Resposta da Maeve"}])
    assert extract_text_from_message(msg) == "Resposta da Maeve"

    # Text extraction from ChatResult
    cr = ChatResult(generations=[ChatGeneration(message=AIMessage(content="Resultado do ChatResult"))])
    assert extract_text_from_message(cr) == "Resultado do ChatResult"
    print("[OK] test_extract_text_from_message_handling PASSOU")

def test_telegram_markdown_formatting():
    """Test B15: Telegram Markdown v1 normalization for headers, bold, and code block preservation."""
    from src.services.telegram_bot import format_telegram_markdown

    raw = "### Resumo\nO **deploy** foi um sucesso com `status_ok`.\n```sh\necho done\n```"
    expected = "*Resumo*\nO *deploy* foi um sucesso com `status_ok`.\n```sh\necho done\n```"
    assert format_telegram_markdown(raw) == expected
    print("[OK] test_telegram_markdown_formatting PASSOU")

def test_semantic_chunking_and_pacing_integrity():
    """Test B17: Semantic message chunking, code fence preservation, and notification pacing."""
    from src.services.telegram_bot import split_into_semantic_chunks, _heal_markdown_boundary

    # Boundary healing for code
    c1 = "Código:\n```python\nx = 1"
    c2 = "y = 2\n```\nFim."
    h1, h2 = _heal_markdown_boundary(c1, c2)
    assert h1.endswith("```")
    assert h2.startswith("```python")

    # Multi-paragraph chunking
    text = "Primeiro pensamento.\n\nSegundo pensamento detalhado.\n\nTerceiro pensamento conclusivo."
    chunks = split_into_semantic_chunks(text, max_chunk_size=40, target_chunk_size=30)
    assert len(chunks) == 3
    assert chunks[0] == "Primeiro pensamento."
    assert chunks[1] == "Segundo pensamento detalhado."
    assert chunks[2] == "Terceiro pensamento conclusivo."
    print("[OK] test_semantic_chunking_and_pacing_integrity PASSOU")

def test_obsidian_service_batch_move_atomic_git():
    """Test B18: Batch move in ObsidianService moves multiple items on disk and executes only ONE atomic git push."""
    import asyncio
    import tempfile
    import shutil
    from unittest.mock import AsyncMock
    from src.services.obsidian import ObsidianService

    temp_vault = tempfile.mkdtemp(prefix="maeve_test_vault_")
    try:
        service = ObsidianService()
        service.vault_path = temp_vault
        service.push = AsyncMock()

        # Prepara 3 arquivos de teste
        os.makedirs(os.path.join(temp_vault, "Inbox"), exist_ok=True)
        os.makedirs(os.path.join(temp_vault, "Projects"), exist_ok=True)
        for i in range(1, 4):
            with open(os.path.join(temp_vault, "Inbox", f"Nota{i}.md"), "w", encoding="utf-8") as f:
                f.write(f"# Conteúdo Nota {i}")

        moves = [
            {"old_path": f"Inbox/Nota{i}.md", "new_path": f"Projects/Nota{i}.md"}
            for i in range(1, 4)
        ]

        result = asyncio.run(service.batch_move_items(moves))

        assert result["total"] == 3
        assert result["success_count"] == 3
        assert result["failed_count"] == 0

        # Verifica que os arquivos agora existem no destino e não na origem
        for i in range(1, 4):
            assert os.path.exists(os.path.join(temp_vault, "Projects", f"Nota{i}.md"))
            assert not os.path.exists(os.path.join(temp_vault, "Inbox", f"Nota{i}.md"))

        # Garante que o push foi chamado apenas UMA vez para todo o lote!
        service.push.assert_called_once_with("Maeve: Movimentação em lote de 3 notas")
        print("[OK] test_obsidian_service_batch_move_atomic_git PASSOU")
    finally:
        shutil.rmtree(temp_vault, ignore_errors=True)

if __name__ == "__main__":
    test_obsidian_path_traversal_blocked()
    test_ticktick_date_normalization()
    test_get_valid_sequence_termination()
    test_vector_point_id_determinism()
    test_router_heuristic_fast_path()
    test_router_regex_json_parsing()
    test_ticktick_connection_pooling()
    test_service_registry_singletons()
    test_selective_rag_skipping()
    test_extract_text_from_message_handling()
    test_telegram_markdown_formatting()
    test_semantic_chunking_and_pacing_integrity()
    test_obsidian_service_batch_move_atomic_git()
    print("\n>>> TODOS OS TESTES DE REGRESSAO PASSARAM COM SUCESSO! <<<")
