"""
Script utilitário para envio de livros locais (PDF/EPUB) para a API da Maeve no Railway
e acompanhamento automático do processamento até a sincronização com o Vault local.

Uso:
    python scripts/upload_book.py "E:\\caminho\\para\\livro.epub" [--polish]
"""
import os
import sys
import time
import argparse
import subprocess
from pathlib import Path
import requests
from dotenv import load_dotenv

# Carrega configurações do .env
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

API_URL = os.getenv("MAEVE_API_URL", "https://context-aware-task-agent-production.up.railway.app").rstrip("/")
API_KEY = os.getenv("API_KEY")
VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", r"E:\mtserik\Documents\MyVault")

def upload_and_monitor(file_path: str, polish_with_llm: bool = False, extract_images: bool = True):
    path = Path(file_path)
    if not path.exists():
        print(f"❌ Erro: Arquivo não encontrado: {file_path}")
        sys.exit(1)

    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    upload_endpoint = f"{API_URL}/api/v1/books/upload"
    print(f"📤 Enviando '{path.name}' para a Maeve no Railway...")
    print(f"   URL: {upload_endpoint}")
    print(f"   Polimento LLM: {'Ativo (GPT-5.6 Luna)' if polish_with_llm else 'Desativado (Zero-Token puro)'}")

    with open(path, "rb") as f:
        files = {"file": (path.name, f)}
        data = {
            "extract_images": str(extract_images).lower(),
            "polish_with_llm": str(polish_with_llm).lower()
        }
        resp = requests.post(upload_endpoint, headers=headers, files=files, data=data)

    if resp.status_code != 202:
        print(f"❌ Erro no upload ({resp.status_code}): {resp.text}")
        sys.exit(1)

    job_data = resp.json()
    job_id = job_data.get("job_id")
    print(f"✅ Upload concluído! Job ID: {job_id}")
    print("⏳ Acompanhando processamento no worker em background...")

    status_endpoint = f"{API_URL}/api/v1/books/status/{job_id}"
    while True:
        time.sleep(5)
        status_resp = requests.get(status_endpoint, headers=headers)
        if status_resp.status_code != 200:
            print(f"⚠️ Erro ao consultar status: {status_resp.text}")
            continue

        st = status_resp.json()
        current_status = st.get("status")
        print(f"   [Status]: {current_status}...")

        if current_status == "SUCCESS":
            print("\n🎉 Livro processado com sucesso!")
            res = st.get("result", {})
            print(f"   - Título: {res.get('title')}")
            print(f"   - Capítulos criados: {res.get('chapter_count')}")
            print(f"   - Anexos extraídos: {res.get('attachments_count')}")
            print(f"   - Vetores no Qdrant: {res.get('vectors_indexed')}")
            print(f"   - MOC: {res.get('moc_path')}")

            # Sincroniza o Vault local se existir
            if os.path.exists(VAULT_PATH):
                print(f"\n🔄 Executando git pull no Vault local ({VAULT_PATH})...")
                try:
                    subprocess.run(["git", "-C", VAULT_PATH, "pull", "origin", "main"], check=True)
                    print("✅ Vault local atualizado com as novas notas e anexos!")
                except Exception as e:
                    print(f"⚠️ Aviso ao atualizar git local: {e}")
            break

        if current_status == "FAILED":
            print(f"\n❌ Falha no processamento: {st.get('error')}")
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Upload de livro para a API da Maeve.")
    parser.add_argument("file_path", help="Caminho completo do arquivo (.epub ou .pdf)")
    parser.add_argument("--polish", action="store_true", help="Ativa polidor cirúrgico LLM com Luna")
    parser.add_argument("--no-images", action="store_true", help="Desativa extração de imagens")

    args = parser.parse_args()
    upload_and_monitor(
        file_path=args.file_path,
        polish_with_llm=args.polish,
        extract_images=not args.no_images
    )

if __name__ == "__main__":
    main()
