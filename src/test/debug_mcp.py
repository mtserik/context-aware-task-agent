import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

async def debug_mcp_endpoint():
    token = os.getenv("TICKTICK_ACCESS_TOKEN")
    url = "https://mcp.ticktick.com"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream"
    }
    
    print(f"--- Debugando GET {url} ---")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url, headers=headers)
            print(f"Status Code: {response.status_code}")
            print(f"Headers: {response.headers}")
            # Se for SSE, o conteúdo pode ser um stream, então não tentamos ler tudo se for longo
            print(f"Content (primeiros 100 bytes): {response.content[:100]}")
        except Exception as e:
            print(f"Erro no GET: {e}")

if __name__ == "__main__":
    asyncio.run(debug_mcp_endpoint())
