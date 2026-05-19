import requests

def run_notion_sync():
    base_url = "http://localhost:8000"
    
    print("🔄 Iniciando sincronização com o Notion...")
    try:
        response = requests.post(f"{base_url}/sync/notion")
        if response.status_code == 200:
            data = response.json()
            if data.get("pages_synced", 0) > 0:
                print(f"✅ Sucesso! {data['pages_synced']} páginas sincronizadas.")
            else:
                print(f"⚠️ {data.get('message', 'Nenhuma página encontrada.')}")
                print("💡 Lembre-se de dar permissão para a integração dentro da página do Notion (Connect to).")
        else:
            print(f"❌ Erro na sincronização: {response.text}")
    except Exception as e:
        print(f"❌ Erro ao conectar na API: {e}")

if __name__ == "__main__":
    run_notion_sync()
