import os
import asyncio
from dotenv import load_dotenv
from src.agent.engine import MaeveAgent, db_service

load_dotenv()

async def test_memory():
    import random
    # ID aleatório para garantir um teste limpo
    session_id = f"test-age-{random.randint(1000, 9999)}"
    print(f"🧠 Testando Memória com ID: {session_id}")
    
    # 1. Inicializar checkpointer
    checkpointer = await db_service.get_checkpointer()
    maeve = MaeveAgent(checkpointer=checkpointer)
    
    print("\n--- SESSÃO 1 ---")
    q1 = "Oi Maeve! Só para você saber, eu tenho 28 anos. Guarde essa informação sobre mim."
    print(f"Você: {q1}")
    r1 = await maeve.run(q1, thread_id=session_id)
    print(f"Maeve: {r1}")
    
    # Fechar pool
    await db_service.close()
    
    print("\n--- REINICIANDO SISTEMA... ---")
    await asyncio.sleep(2)
    
    # 2. Reinicializar tudo
    from src.services.database import DatabaseService
    new_db = DatabaseService()
    new_checkpointer = await new_db.get_checkpointer()
    new_maeve = MaeveAgent(checkpointer=new_checkpointer)
    
    print("\n--- SESSÃO 2 ---")
    q2 = "Você lembra quantos anos eu tenho?"
    print(f"Você: {q2}")
    r2 = await new_maeve.run(q2, thread_id=session_id)
    print(f"Maeve: {r2}")
    
    if "28" in r2:
        print("\n✅ SUCESSO: A Maeve lembrou da sua idade via Supabase!")
    else:
        print("\n❌ FALHA: A Maeve não lembrou do contexto.")
    
    await new_db.close()

if __name__ == "__main__":
    asyncio.run(test_memory())
