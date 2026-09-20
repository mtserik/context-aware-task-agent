"""
Script para processamento em lote dos livros e expansões de Ordem Paranormal RPG.
Executa o pipeline Zero-Token, particionamento de capítulos, escrita no Obsidian Vault,
indexação semântica no Qdrant Cloud e commit/push Git.
"""
import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Carrega variáveis de ambiente do .env
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)

from src.services.registry import get_book_domain_service

BOOKS_TO_INGEST = [
    r"E:\mtserik\Documents\RPGs\Ordem Paranormal\Sobrevivendo-ao-Horror-v1-3.pdf",
    r"E:\mtserik\Documents\RPGs\Ordem Paranormal\Casos Paranormais\Casos Paranormais.pdf",
    r"E:\mtserik\Documents\RPGs\Ordem Paranormal\Casos Paranormais\O Voo da Morte.pdf",
    r"E:\mtserik\Documents\RPGs\Ordem Paranormal\Casos Paranormais\Missao Extra 2 - Brumas de Vento Baixo.pdf"
]

async def process_all():
    domain = get_book_domain_service()
    total = len(BOOKS_TO_INGEST)
    results = []

    print(f"🚀 Iniciando processamento em lote de {total} obras de Ordem Paranormal...")
    print("=" * 60)

    for idx, book_path in enumerate(BOOKS_TO_INGEST, start=1):
        p = Path(book_path)
        if not p.exists():
            print(f"[{idx}/{total}] ⚠️ Arquivo não encontrado: {book_path}")
            continue

        print(f"\n[{idx}/{total}] 📖 Processando: {p.name}")
        try:
            res = await domain.ingest_book(
                file_path=str(p),
                mode="rpg",
                extract_images=True,
                sync_git=True,
                sync_vector_db=True,
                polish_with_llm=False
            )
            results.append(res)
            print(f"  ✅ Concluído: '{res['title']}'")
            print(f"     - Capítulos: {res['chapter_count']}")
            print(f"     - Anexos/Imagens: {res['attachments_count']}")
            print(f"     - Vetores Qdrant: {res['vectors_indexed']}")
            print(f"     - MOC: {res['moc_path']}")
        except Exception as e:
            print(f"  ❌ Erro ao processar '{p.name}': {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"🏁 Processamento em lote finalizado! {len(results)}/{total} livros ingeridos com sucesso.")
    return results

if __name__ == "__main__":
    asyncio.run(process_all())
