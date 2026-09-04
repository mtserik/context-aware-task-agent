import os
import asyncio
import socket
import json
import urllib.parse as urlparse
from typing import Any
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

class DatabaseService:
    """
    Versão Industrial para Supabase (IPv4 Direct).
    """
    def __init__(self):
        self.connection_string = os.getenv("SUPABASE_DB_URL")
        self.pool = None
        self._checkpointer = None

    async def get_pool(self) -> AsyncConnectionPool:
        if self.pool is None:
            if not self.connection_string:
                raise Exception("SUPABASE_DB_URL não configurada")
            
            # 1. Resolve Hostname para IPv4 manualmente para evitar erro de rede no Docker
            conn_info = self.connection_string.strip()
            try:
                url = urlparse.urlparse(conn_info)
                # Só tenta resolver se não for um IP puro
                if url.hostname and not url.hostname.replace('.', '').isdigit():
                    ipv4 = socket.gethostbyname(url.hostname)
                    conn_info = conn_info.replace(f"@{url.hostname}", f"@{ipv4}", 1)
                    print(f"📡 DNS: {url.hostname} -> {ipv4}")
            except Exception as e:
                print(f"⚠️ DNS Bypass: {e}")

            # 2. Configurações de estabilidade
            if "sslmode" not in conn_info:
                conn_info += ("&" if "?" in conn_info else "?") + "sslmode=require"

            self.pool = AsyncConnectionPool(
                conninfo=conn_info,
                max_size=10,
                kwargs={"prepare_threshold": 0},
                open=False,
                reconnect_timeout=10,
                check=AsyncConnectionPool.check_connection
            )
            await self.pool.open()
            print("✅ Conexão SQL ativa.")
                
        return self.pool

    async def get_checkpointer(self) -> AsyncPostgresSaver:
        try:
            if self._checkpointer is None:
                pool = await self.get_pool()
                # 1. Garante que as tabelas customizadas existam
                await self._setup_custom_tables()
                
                # 2. Setup do checkpointer
                self._checkpointer = AsyncPostgresSaver(pool)
                await self._checkpointer.setup()
            return self._checkpointer
        except Exception as e:
            print(f"❌ Erro ao obter checkpointer: {e}")
            self.pool = None # Força reinicialização do pool na próxima tentativa
            self._checkpointer = None
            raise e

    async def _setup_custom_tables(self):
        """Cria as tabelas de lembretes e preferências se elas não existirem."""
        pool = await self.get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # Extensão uuid-ossp
                await cur.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
                
                # Tabela de Lembretes
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS reminders (
                        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                        user_id TEXT NOT NULL,
                        chat_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        reminder_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        is_completed BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        metadata JSONB DEFAULT '{}'::jsonb
                    )
                """)
                await cur.execute("CREATE INDEX IF NOT EXISTS idx_reminders_reminder_at ON reminders(reminder_at) WHERE is_completed = FALSE")
                await cur.execute("CREATE INDEX IF NOT EXISTS idx_reminders_user_id ON reminders(user_id)")
                
                # Tabela de Preferências
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_preferences (
                        user_id TEXT PRIMARY KEY,
                        preferences JSONB DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                print("✅ Tabelas customizadas verificadas/criadas.")

    async def close(self):
        if self.pool:
            await self.pool.close()

    # --- Métodos de Lembretes ---
    async def create_reminder(self, user_id: str, chat_id: str, content: str, reminder_at: str, metadata: dict = None):
        """Cria um novo lembrete no banco de dados."""
        pool = await self.get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO reminders (user_id, chat_id, content, reminder_at, metadata) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (user_id, chat_id, content, reminder_at, json.dumps(metadata or {}))
                )
                res = await cur.fetchone()
                return res[0]

    async def get_pending_reminders(self):
        """Busca todos os lembretes pendentes que já passaram da hora."""
        pool = await self.get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, user_id, chat_id, content, metadata FROM reminders WHERE is_completed = FALSE AND reminder_at <= CURRENT_TIMESTAMP"
                )
                return await cur.fetchall()

    async def mark_reminder_completed(self, reminder_id: str):
        """Marca um lembrete como concluído."""
        pool = await self.get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("UPDATE reminders SET is_completed = TRUE WHERE id = %s", (reminder_id,))

    async def list_user_reminders(self, user_id: str):
        """Lista todos os lembretes ativos de um usuário."""
        pool = await self.get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT content, reminder_at FROM reminders WHERE user_id = %s AND is_completed = FALSE ORDER BY reminder_at ASC",
                    (user_id,)
                )
                return await cur.fetchall()

    # --- Métodos de Preferências ---
    async def get_user_preference(self, user_id: str, key: str, default: Any = None):
        """Busca uma preferência específica do usuário."""
        pool = await self.get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT preferences FROM user_preferences WHERE user_id = %s", (user_id,))
                res = await cur.fetchone()
                if res and res[0]:
                    prefs = res[0]
                    if isinstance(prefs, str):
                        try:
                            prefs = json.loads(prefs)
                        except Exception:
                            prefs = {}
                    if isinstance(prefs, dict):
                        return prefs.get(key, default)
                return default

    async def update_user_preference(self, user_id: str, key: str, value: Any):
        """Atualiza ou cria uma preferência para o usuário."""
        pool = await self.get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # Busca preferências atuais
                await cur.execute("SELECT preferences FROM user_preferences WHERE user_id = %s", (user_id,))
                res = await cur.fetchone()
                
                prefs = res[0] if res and res[0] else {}
                if isinstance(prefs, str):
                    try:
                        prefs = json.loads(prefs)
                    except Exception:
                        prefs = {}
                if not isinstance(prefs, dict):
                    prefs = {}
                prefs[key] = value
                
                await cur.execute(
                    "INSERT INTO user_preferences (user_id, preferences) VALUES (%s, %s) "
                    "ON CONFLICT (user_id) DO UPDATE SET preferences = EXCLUDED.preferences, updated_at = CURRENT_TIMESTAMP",
                    (user_id, json.dumps(prefs))
                )
