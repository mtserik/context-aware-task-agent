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

if __name__ == "__main__":
    test_dynamic_tool_binding_subsets()
    test_task_domain_parent_project_inheritance()
    test_task_domain_time_blocking_normalization()
    test_knowledge_domain_note_creation()
    test_fastapi_endpoints_health()
    print("\n>>> TODOS OS TESTES UNITARIOS DE DOMINIO PASSARAM! <<<")
