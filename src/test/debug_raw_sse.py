import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

async def debug_raw_sse():
    token = os.getenv("TICKTICK_ACCESS_TOKEN")
    url = "https://mcp.ticktick.com"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive"
    }
    
    print(f"--- Lendo SSE Bruto de {url} ---")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            async with client.stream("GET", url, headers=headers) as response:
                print(f"Status: {response.status_code}")
                async for line in response.aiter_lines():
                    print(f"SSE: {line}")
        except Exception as e:
            print(f"Erro: {e}")

if __name__ == "__main__":
    asyncio.run(debug_raw_sse())
