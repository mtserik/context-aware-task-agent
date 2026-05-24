import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

async def debug_mcp_h2():
    token = os.getenv("TICKTICK_ACCESS_TOKEN")
    url = "https://mcp.ticktick.com"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream"
    }
    
    print(f"--- Debugando GET {url} (HTTP/2) ---")
    async with httpx.AsyncClient(http2=True, timeout=10.0) as client:
        try:
            async with client.stream("GET", url, headers=headers) as response:
                print(f"Status Code: {response.status_code}")
                print(f"HTTP Version: {response.http_version}")
                print(f"Headers: {response.headers}")
                async for line in response.aiter_lines():
                    print(f"Line: {line}")
                    if line: break # Pega apenas a primeira linha
        except Exception as e:
            print(f"Erro no GET H2: {e}")

if __name__ == "__main__":
    asyncio.run(debug_mcp_h2())
