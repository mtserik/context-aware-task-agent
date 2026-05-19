import requests

def interactive_chat():
    base_url = "http://localhost:8000"
    print("🤖 Bem-vindo ao Chat com a Maeve!")
    print("Digite sua pergunta sobre o seu Second Brain (ou 'sair' para encerrar).\n")

    while True:
        user_input = input("Você: ")
        if user_input.lower() in ["sair", "exit", "quit"]:
            break

        try:
            response = requests.post(
                f"{base_url}/chat", 
                json={"message": user_input}
            )
            if response.status_code == 200:
                answer = response.json().get("response")
                print(f"\n🤖 Maeve: {answer}\n")
            else:
                print(f"❌ Erro: {response.text}")
        except Exception as e:
            print(f"❌ Erro de conexão: {e}")

if __name__ == "__main__":
    interactive_chat()
