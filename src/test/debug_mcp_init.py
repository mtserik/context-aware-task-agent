import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

async def debug_mcp_initialize():
    token = os.getenv("TICKTICK_ACCESS_TOKEN")
    url = "https://mcp.ticktick.com"
    
    # Mensagem de inicialização padrão do MCP
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "Maeve-Client",
                "version": "1.0.0"
            }
        }
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    print(f"--- Tentando initialize via POST {url} ---")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
        except Exception as e:
            print(f"Erro: {e}")

if __name__ == "__main__":
    asyncio.run(debug_mcp_initialize())
