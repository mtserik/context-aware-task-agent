import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.services.ticktick import TickTickService

async def test_general_completions():
    print("🚀 Testando contador geral de tarefas concluídas...")
    service = TickTickService()
    
    # Vamos rodar o teste com a lógica padrão (mês vigente)
    try:
        completed = await service.get_all_completed_tasks()
        print(f"✅ Conexão bem-sucedida com o endpoint de dados!")
        print(f"📊 Total de tarefas comuns concluídas localizadas em Maio: {len(completed)}")
        
        if len(completed) > 0:
            print("\n📋 Amostra das últimas tarefas fechadas:")
            for t in completed[:5]:
                print(f"  - [X] {t.get('title')} (Modificado em: {t.get('modifiedTime')})")
                
    except Exception as e:
        print(f"❌ Falha no teste: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_general_completions())