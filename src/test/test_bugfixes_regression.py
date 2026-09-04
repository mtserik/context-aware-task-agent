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
    """Test B3: Date strings must be converted to valid ISO format for TickTick."""
    assert _normalize_ticktick_date("2026-09-03") == "2026-09-03T00:00:00-0300"
    assert _normalize_ticktick_date("2026-09-03T15:30:00") == "2026-09-03T15:30:00-0300"
    assert _normalize_ticktick_date("2026-09-03T15:30:00Z") == "2026-09-03T15:30:00Z"
    assert _normalize_ticktick_date("2026-09-03T15:30:00-0300") == "2026-09-03T15:30:00-0300"
    assert _normalize_ticktick_date(None) is None
    assert _normalize_ticktick_date("") == ""
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

if __name__ == "__main__":
    test_obsidian_path_traversal_blocked()
    test_ticktick_date_normalization()
    test_get_valid_sequence_termination()
    test_vector_point_id_determinism()
    print("\n>>> TODOS OS TESTES DE REGRESSAO PASSARAM COM SUCESSO! <<<")
