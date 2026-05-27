import asyncio
import os
from dotenv import load_dotenv
from src.services.ticktick import TickTickService

async def main():
    load_dotenv()
    ticktick = TickTickService()
    
    print("--- Listing MCP Tools ---")
    try:
        tools = await ticktick.list_mcp_tools()
        for tool in tools:
            print(f"\nTool: {tool['name']}")
            print(f"Description: {tool['description']}")
            print(f"Schema: {tool['schema']}")
    except Exception as e:
        print(f"Error listing MCP tools: {e}")

if __name__ == "__main__":
    asyncio.run(main())
