import unittest
import asyncio
import os
import sys
import tempfile
import shutil
from unittest.mock import AsyncMock, MagicMock, patch, call

for mod_name in [
    "httpx", "qdrant_client", "qdrant_client.models",
    "langchain_openai", "langchain_core", "langchain_core.messages",
    "pydantic", "fastapi", "psycopg_pool", "psycopg",
    "langgraph", "langgraph.checkpoint", "langgraph.checkpoint.postgres",
    "langgraph.checkpoint.postgres.aio", "tavily", "telegram", "telegram.ext"
]:
    if mod_name not in sys.modules:
        m = MagicMock()
        if mod_name == "qdrant_client.models":
            m.Distance = MagicMock()
            m.VectorParams = MagicMock()
            def make_point(**kwargs):
                mock_pt = MagicMock()
                mock_pt.id = kwargs.get("id")
                mock_pt.vector = kwargs.get("vector")
                mock_pt.payload = kwargs.get("payload")
                return mock_pt
            m.PointStruct = make_point
            m.Filter = MagicMock()
            m.FieldCondition = MagicMock()
            m.MatchValue = MagicMock()
        sys.modules[mod_name] = m

from src.services.obsidian import ObsidianService


class TestGitResilience(unittest.IsolatedAsyncioTestCase):
    """
    Testes de resiliência e auto-recuperação do Git no ObsidianService:
    - Prevenção e expurgo de locks órfãos (index.lock, rebase-merge, MERGE_HEAD).
    - Auto-recuperação atômica em falha de rebase / status 128 (shallow trees).
    - Sincronização prévia (sync-before-write) para eliminar divergências de branch.
    """

    async def test_cleanup_git_locks(self):
        """Valida a limpeza determinística de index.lock e pastas residuais de rebase."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = ObsidianService()
            service.vault_path = tmp_dir
            git_dir = os.path.join(tmp_dir, ".git")
            os.makedirs(git_dir, exist_ok=True)

            # Cria arquivos/pastas de bloqueio
            index_lock = os.path.join(git_dir, "index.lock")
            with open(index_lock, "w") as f:
                f.write("lock")

            rebase_merge = os.path.join(git_dir, "rebase-merge")
            os.makedirs(rebase_merge, exist_ok=True)

            merge_head = os.path.join(git_dir, "MERGE_HEAD")
            with open(merge_head, "w") as f:
                f.write("commit_hash")

            self.assertTrue(os.path.exists(index_lock))
            self.assertTrue(os.path.exists(rebase_merge))
            self.assertTrue(os.path.exists(merge_head))

            # Executa a limpeza
            service._cleanup_git_locks()

            self.assertFalse(os.path.exists(index_lock))
            self.assertFalse(os.path.exists(rebase_merge))
            self.assertFalse(os.path.exists(merge_head))

    async def test_write_note_calls_sync_before_writing(self):
        """Valida que write_note sincroniza com o remoto antes de alterar o disco se houver commit_message."""
        service = ObsidianService()
        service.sync = AsyncMock()
        service.push = AsyncMock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            service.vault_path = tmp_dir
            rel_path = "Inbox/NovaNota.md"
            content = "# Minha Nota"

            await service.write_note(rel_path, content, commit_message="Maeve: Teste")

            # Verifica que sync foi chamado ANTES de push
            service.sync.assert_awaited_once()
            service.push.assert_awaited_once_with("Maeve: Teste")

            # Verifica que o arquivo foi escrito
            written_file = os.path.join(tmp_dir, "Inbox", "NovaNota.md")
            self.assertTrue(os.path.exists(written_file))
            with open(written_file, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), content)

    async def test_push_atomic_reconciliation_on_rebase_failure(self):
        """
        Valida que se o push direto for rejeitado e o rebase falhar (erro 128 / unrelated histories),
        o fallback atômico restaura os arquivos modificados sobre a ponta do remoto e envia com sucesso.
        """
        service = ObsidianService()

        with tempfile.TemporaryDirectory() as tmp_dir:
            service.vault_path = tmp_dir
            git_dir = os.path.join(tmp_dir, ".git")
            os.makedirs(git_dir, exist_ok=True)

            # Cria arquivo de teste no vault
            test_file = os.path.join(tmp_dir, "Inbox", "NotaTeste.md")
            os.makedirs(os.path.dirname(test_file), exist_ok=True)
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("# Conteúdo da Nota Teste")

            call_counts = {"push": 0}

            async def fake_run_git(args):
                cmd = args[0]
                if cmd == "branch":
                    return "main"
                if cmd == "status":
                    return "M Inbox/NotaTeste.md"
                if cmd == "commit":
                    return "[main 12345] commit ok"
                if cmd == "push":
                    call_counts["push"] += 1
                    if call_counts["push"] == 1:
                        # Primeiro push falha (non-fast-forward / rejected)
                        raise Exception("rejected (fetch first)")
                    else:
                        # Segundo push (após reconciliação atômica) tem sucesso!
                        return "Everything up-to-date"
                if cmd == "fetch":
                    return "fetch ok"
                if cmd == "rebase":
                    # Rebase falha com o erro 128 (unrelated histories em shallow)
                    raise Exception("fatal: refusing to merge unrelated histories (exit code 128)")
                if cmd == "diff-tree":
                    return "Inbox/NotaTeste.md\n"
                if cmd == "reset":
                    return "HEAD is now at origin/main"
                return ""

            with patch.object(service, "_run_git", side_effect=fake_run_git):
                # Executa o push
                await service.push("Maeve: Teste de Resiliência")

                # Push deve ter sido chamado 2 vezes (primeira falha, segunda pós-reconciliação atômica)
                self.assertEqual(call_counts["push"], 2)


if __name__ == "__main__":
    unittest.main()
