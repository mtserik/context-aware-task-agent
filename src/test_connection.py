import requests
import time

def test_maeve_flow():
    base_url = "http://localhost:8000"
    
    print("🔍 Verificando se a Maeve está online...")
    try:
        response = requests.get(f"{base_url}/")
        print(f"✅ Status: {response.json()}")
    except Exception as e:
        print(f"❌ Erro ao conectar na API: {e}")
        return

    # No futuro, poderíamos adicionar um endpoint de ingestão.
    # Por enquanto, o agente tenta buscar, mas o banco estará vazio.
    
    print("\n💬 Enviando mensagem de teste para a Maeve...")
    chat_payload = {"message": "Quem é você e o que você sabe sobre o meu Second Brain?"}
    try:
        start_time = time.time()
        chat_response = requests.post(f"{base_url}/chat", json=chat_payload)
        end_time = time.time()
        
        if chat_response.status_code == 200:
            print(f"🤖 Maeve respondeu em {end_time - start_time:.2f}s:")
            print(f"---\n{chat_response.json()['response']}\n---")
            print("\n💡 Nota: Se o banco estiver vazio, ela responderá de forma genérica.")
        else:
            print(f"❌ Erro na resposta do chat: {chat_response.text}")
    except Exception as e:
        print(f"❌ Erro ao enviar mensagem: {e}")

if __name__ == "__main__":
    test_maeve_flow()
