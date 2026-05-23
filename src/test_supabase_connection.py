import os
import asyncio
from dotenv import load_dotenv
from src.services.database import DatabaseService

load_dotenv()

async def test_connection():
    db = DatabaseService()
    print("🚀 Testando conexão com Supabase...")
    try:
        pool = await db.get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT version();")
                version = await cur.fetchone()
                print(f"✅ Conectado ao PostgreSQL: {version[0]}")
                
                await cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
                tables = await cur.fetchall()
                print(f"📋 Tabelas encontradas: {[t[0] for t in tables]}")
        
        checkpointer = await db.get_checkpointer()
        print("✅ Checkpointer do LangGraph inicializado com sucesso.")
        
    except Exception as e:
        print(f"❌ Erro na conexão: {e}")
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(test_connection())
