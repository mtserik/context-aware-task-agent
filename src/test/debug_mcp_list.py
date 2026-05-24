import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

async def debug_mcp_list_tools():
    token = os.getenv("TICKTICK_ACCESS_TOKEN")
    url = "https://mcp.ticktick.com"
    
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    print(f"--- Listando tools via POST {url} ---")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            print(f"Status: {response.status_code}")
            import json
            print(json.dumps(response.json(), indent=2))
        except Exception as e:
            print(f"Erro: {e}")

if __name__ == "__main__":
    asyncio.run(debug_mcp_list_tools())
