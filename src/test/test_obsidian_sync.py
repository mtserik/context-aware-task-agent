import requests
import os

def run_obsidian_sync():
    base_url = "http://localhost:8000"
    
    print("🔄 Iniciando sincronização com o Vault do Obsidian via Git...")
    try:
        response = requests.post(f"{base_url}/sync/obsidian")
        if response.status_code == 200:
            data = response.json()
            if data.get("notes_synced", 0) > 0:
                print(f"✅ Sucesso! {data['notes_synced']} notas sincronizadas e indexadas no Qdrant.")
            else:
                print(f"⚠️ {data.get('message', 'Nenhuma nota encontrada.')}")
        else:
            print(f"❌ Erro na sincronização: {response.text}")
    except Exception as e:
        print(f"❌ Erro ao conectar na API: {e}")

if __name__ == "__main__":
    run_obsidian_sync()
