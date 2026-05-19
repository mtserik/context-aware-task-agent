from src.services.ticktick import TickTickService
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def setup():
    service = TickTickService()
    print("=== Setup TickTick para Maeve ===\n")
    print("1. Acesse esta URL no seu navegador e autorize a Maeve:")
    print("-" * 30)
    print(service.get_authorization_url())
    print("-" * 30)
    
    print("\n💡 Dica: Se você não configurou um servidor de callback, a página dará erro após autorizar.")
    print("Isso é normal! Apenas copie o valor do parâmetro '?code=' que aparecerá na barra de endereços.")
    
    code = input("\n2. Cole o valor do 'code' aqui: ")
    
    try:
        token_data = await service.get_access_token(code)
        print("\n✅ Sucesso! Seu ACCESS_TOKEN é:")
        print("-" * 30)
        print(token_data.get("access_token"))
        print("-" * 30)
        print("\n👉 COPIE E COLE NO SEU ARQUIVO .env:")
        print(f"TICKTICK_ACCESS_TOKEN={token_data.get('access_token')}")
    except Exception as e:
        print(f"\n❌ Erro ao obter token: {e}")

if __name__ == "__main__":
    asyncio.run(setup())
