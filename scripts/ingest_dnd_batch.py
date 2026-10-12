"""
Script para processamento em lote dos livros e expansões de D&D 5e.
Executa o pipeline Zero-Token, particionamento de capítulos, escrita no Obsidian Vault em Recursos/Livros,
indexação semântica no Qdrant Cloud e commit/push Git atômico por obra.
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

DND_BOOKS = [
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\dd-5e-guia-de-classe-ninja-biblioteca-elfica.pdf",
        "title": "D&D 5e - Guia de Classe Ninja"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\dd-5e-regras-basicas-dos-mestres-biblioteca-elfica.pdf",
        "title": "D&D 5e - Regras Básicas dos Mestres"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\dd-5e-regras-basicas-dos-jogadores-biblioteca-elfica.pdf",
        "title": "D&D 5e - Regras Básicas dos Jogadores"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\dd-5e-tomo-de-batalha-o-livro-das-nove-espadas-biblioteca-elfica.pdf",
        "title": "D&D 5e - Tomo de Batalha (O Livro das Nove Espadas)"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\a-mina-perdida-de-phandelver-v1-7.pdf",
        "title": "D&D 5e - A Mina Perdida de Phandelver"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\dd-5e-guia-do-mestre-biblioteca-elfica.pdf",
        "title": "D&D 5e - Guia do Mestre"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\dd-5e-livro-do-jogador-fundo-branco-biblioteca-elfica.pdf",
        "title": "D&D 5e - Livro do Jogador"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\dd-5e-compendio-de-magia-fundo-colorido-biblioteca-elfica.pdf",
        "title": "D&D 5e - Compêndio de Magias"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\dd-5e-os-segredos-que-se-escondem-em-evernura.pdf",
        "title": "D&D 5e - Os Segredos Que Se Escondem em Evernura"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\old-dd-5e-manual-dos-monstros-biblioteca-elfica.pdf",
        "title": "D&D 5e - Manual dos Monstros (Edição Legada)"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\dd-5e-guia-de-xanathar-para-todas-as-coisas-fundo-colorido-biblioteca-elfica.pdf",
        "title": "D&D 5e - Guia de Xanathar para Todas as Coisas"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\dd-5e-guia-do-volo-para-monstros-v-alta-resolucao-biblioteca-elfica.pdf",
        "title": "D&D 5e - Guia do Volo para Monstros"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\dd-5e-runeterra-league-of-legends-rpg-v-1-01-biblioteca-elfica.pdf",
        "title": "D&D 5e - Suplemento Runeterra (League of Legends)"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\dd-5e-manual-dos-monstros-dd-beyond-2-1-biblioteca-elfica.pdf",
        "title": "D&D 5e - Manual dos Monstros"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\dampd-5e---livro-do-jogador-2024.pdf",
        "title": "D&D 5e - Livro do Jogador (2024)"
    },
    {
        "path": r"E:\mtserik\Documents\RPGs\D&D\tashas-cauldron-of-everything.pdf",
        "title": "D&D 5e - Caldeirão de Todas as Coisas de Tasha"
    }
]

async def process_all(single_book: str = None):
    domain = get_book_domain_service()
    books = [b for b in DND_BOOKS if single_book is None or single_book in b["title"]]
    total = len(books)
    results = []

    print(f"🚀 Iniciando processamento de {total} obras de D&D 5e...")
    print("=" * 60)

    for idx, item in enumerate(books, start=1):
        book_path = item["path"]
        custom_title = item["title"]
        p = Path(book_path)
        if not p.exists():
            print(f"[{idx}/{total}] ⚠️ Arquivo não encontrado: {book_path}")
            continue

        vault_dir = Path(os.getenv("OBSIDIAN_VAULT_PATH", r"E:\mtserik\Documents\MyVault"))
        moc_file = vault_dir / "Recursos" / "Livros" / custom_title / f"{custom_title}.md"
        if moc_file.exists():
            print(f"[{idx}/{total}] ⏩ Já ingerido anteriormente: '{custom_title}' (MOC existe). Pulando.")
            continue

        print(f"\n[{idx}/{total}] 📖 Processando: '{custom_title}' ({p.stat().st_size / (1024*1024):.1f} MB)")
        try:
            res = await domain.ingest_book(
                file_path=str(p),
                title=custom_title,
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
            print(f"  ❌ Erro ao processar '{custom_title}': {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"🏁 Processamento finalizado! {len(results)}/{total} livros ingeridos com sucesso.")
    return results

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(process_all(target))
