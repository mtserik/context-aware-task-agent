import asyncio
import os
from dotenv import load_dotenv
from src.services.ticktick import TickTickService

load_dotenv()

async def test_hybrid():
    service = TickTickService()
    
    print("--- Testando API REST (Tarefas) ---")
    try:
        tasks = await service.get_tasks()
        print(f"✅ Sucesso! Encontradas {len(tasks)} tarefas pendentes.")
    except Exception as e:
        print(f"❌ Erro na API REST: {e}")

    print("\n--- Testando MCP (Hábitos) ---")
    try:
        habits = await service.get_habits()
        print(f"✅ Sucesso! Hábitos recuperados via MCP.")
        print(f"Conteúdo (resumo): {habits[:200]}...")
    except Exception:
        import traceback
        print(f"❌ Erro no MCP (Hábitos):")
        traceback.print_exc()

    print("\n--- Testando MCP (Histórico de Tarefas) ---")
    try:
        history = await service.get_completed_tasks_history()
        print(f"✅ Sucesso! Histórico recuperado via MCP.")
        print(f"Conteúdo (resumo): {history[:200]}...")
    except Exception:
        import traceback
        print(f"❌ Erro no MCP (Histórico):")
        traceback.print_exc()

    print("\n--- Testando MCP (Listagem de Ferramentas) ---")
    try:
        mcp_tools = await service.list_mcp_tools()
        print(f"✅ Sucesso! {len(mcp_tools)} ferramentas encontradas no MCP.")
        for t in mcp_tools:
            print(f" - {t['name']}: {t['description']}")
    except Exception as e:
        print(f"❌ Erro ao listar ferramentas MCP: {e}")

if __name__ == "__main__":
    asyncio.run(test_hybrid())
