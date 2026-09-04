import asyncio
import os
from dotenv import load_dotenv
from src.services.ticktick import TickTickService
from datetime import datetime
from src.domain.temporal import get_local_now

load_dotenv()

async def debug_ticktick_tasks():
    service = TickTickService()
    try:
        print("🔍 Buscando todas as tarefas do TickTick...")
        tasks = await service.get_tasks()
        print(f"📊 Total de tarefas encontradas: {len(tasks)}")
        
        today_str = get_local_now().strftime('%Y-%m-%d')
        print(f"📅 Data de hoje para o filtro: {today_str}")
        
        for i, task in enumerate(tasks[:10]): # Mostra as 10 primeiras
            print(f"\nTarefa {i+1}:")
            print(f"  Título: {task.get('title')}")
            print(f"  Status: {task.get('status')} (0 = aberto, 2 = concluído)")
            print(f"  DueDate: {task.get('dueDate')}")
            
        today_tasks = [t for t in tasks if t.get('dueDate') and t['dueDate'].startswith(today_str)]
        print(f"\n✅ Tarefas que passaram no filtro de HOJE: {len(today_tasks)}")
        for t in today_tasks:
            print(f"  - {t.get('title')}")

    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    asyncio.run(debug_ticktick_tasks())
