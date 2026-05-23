import os
import asyncio
import socket
import urllib.parse as urlparse
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
                if not url.hostname.replace('.', '').isdigit():
                    ipv4 = socket.gethostbyname(url.hostname)
                    conn_info = conn_info.replace(url.hostname, ipv4)
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
                open=False
            )
            await self.pool.open()
            print("✅ Conexão SQL ativa.")
                
        return self.pool

    async def get_checkpointer(self) -> AsyncPostgresSaver:
        if self._checkpointer is None:
            pool = await self.get_pool()
            self._checkpointer = AsyncPostgresSaver(pool)
            await self._checkpointer.setup()
        return self._checkpointer

    async def close(self):
        if self.pool:
            await self.pool.close()
