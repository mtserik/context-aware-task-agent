import unittest
import asyncio
import os
import sys
import tempfile
import shutil
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

# Garante mocks no sys.modules para bibliotecas de terceiros se não estiverem instaladas no host
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

from src.domain.models import KnowledgeResult


class TestZeroDiskSyncArchitecture(unittest.IsolatedAsyncioTestCase):
    """
    Testes unitários para validar a arquitetura ultra-leve (shallow + sparse)
    do ObsidianService e a sincronização incremental do KnowledgeDomainService/VectorDBService.
    """

    async def test_obsidian_sparse_checkout_configuration(self):
        """Valida que o sparse-checkout configura o arquivo de exclusão de binários pesados."""
        from src.services.obsidian import ObsidianService

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = ObsidianService()
            service.vault_path = tmp_dir
            git_info_dir = os.path.join(tmp_dir, ".git", "info")
            os.makedirs(git_info_dir, exist_ok=True)

            with patch.object(service, "_run_git_sync") as mock_git_sync:
                service._configure_sparse_checkout()

                # Verifica que o comando de ativação do sparse checkout foi chamado
                mock_git_sync.assert_called_with(["config", "core.sparseCheckout", "true"])

            # Verifica o conteúdo do arquivo sparse-checkout
            sparse_file = os.path.join(git_info_dir, "sparse-checkout")
            self.assertTrue(os.path.exists(sparse_file))
            with open(sparse_file, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("/*", content)
            self.assertIn("!**/attachments/", content)
            self.assertIn("!*.png", content)
            self.assertIn("!*.jpg", content)
            self.assertIn("!*.pdf", content)

    async def test_obsidian_is_shallow_detection(self):
        """Valida a detecção de repositório shallow."""
        from src.services.obsidian import ObsidianService
        service = ObsidianService()

        with patch.object(service, "_run_git", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "true\n"
            self.assertTrue(await service._is_shallow())

            mock_run.return_value = "false\n"
            self.assertFalse(await service._is_shallow())

    async def test_vector_db_batching_and_hashing(self):
        """Valida que o upsert_documents aplica batching e gera hash SHA-256 no payload."""
        from src.services.vector_db import VectorDBService
        vdb = VectorDBService()

        mock_client = AsyncMock()
        mock_client.upsert = AsyncMock()
        vdb.client = mock_client
        vdb.embeddings = AsyncMock()
        vdb.embeddings.aembed_documents = AsyncMock(return_value=[[0.1] * 1536, [0.2] * 1536])

        texts = ["Nota 1 de teste", "Nota 2 de teste"]
        metas = [{"path": "01 - Daily/2026-10-05.md"}, {"path": "Projetos/Maeve.md"}]

        await vdb.upsert_documents(texts, metas, batch_size=1)

        # Como batch_size=1 e temos 2 notas, upsert deve ter sido chamado 2 vezes
        self.assertEqual(mock_client.upsert.call_count, 2)

        # Checa o ponto gerado na primeira chamada
        first_call_points = mock_client.upsert.call_args_list[0].kwargs["points"]
        first_payload = first_call_points[0].payload
        expected_hash = hashlib.sha256("Nota 1 de teste".encode("utf-8")).hexdigest()
        self.assertEqual(first_payload["content_hash"], expected_hash)
        self.assertEqual(first_payload["path"], "01 - Daily/2026-10-05.md")

    async def test_vector_db_get_by_path(self):
        """Valida recuperação direta por path determinístico no Qdrant."""
        from src.services.vector_db import VectorDBService
        vdb = VectorDBService()

        mock_point = MagicMock()
        mock_point.payload = {"content": "Conteúdo da nota", "path": "Decisoes/ADR.md"}

        mock_client = AsyncMock()
        mock_client.retrieve = AsyncMock(return_value=[mock_point])
        vdb.client = mock_client

        doc = await vdb.get_by_path("Decisoes/ADR.md")
        self.assertIsNotNone(doc)
        self.assertEqual(doc["content"], "Conteúdo da nota")

    async def test_knowledge_domain_get_note_content_prefers_qdrant(self):
        """Valida que get_note_content consulta prioritariamente o Qdrant."""
        from src.domain.knowledge import KnowledgeDomainService

        mock_obsidian = AsyncMock()
        mock_obsidian.vault_path = "/mock/vault"
        mock_vdb = AsyncMock()
        mock_vdb.get_by_path = AsyncMock(return_value={"content": "Texto rápido do Qdrant", "path": "teste.md"})

        service = KnowledgeDomainService(obsidian_service=mock_obsidian, vector_db_service=mock_vdb)
        result = await service.get_note_content("teste.md")

        self.assertTrue(result.success)
        self.assertEqual(result.message, "Texto rápido do Qdrant")
        # Garante que o disco nem foi tocado
        mock_obsidian.get_note_content.assert_not_called()

    async def test_knowledge_domain_sync_incremental(self):
        """Valida que o sync_knowledge pula notas com hash idêntico e remove deletadas."""
        from src.domain.knowledge import KnowledgeDomainService

        mock_obsidian = AsyncMock()
        mock_obsidian.vault_path = "/mock/vault"
        mock_obsidian.sync = AsyncMock()
        mock_obsidian.push = AsyncMock()
        # Temos 2 notas no repositório: Nota 1 (inalterada) e Nota 2 (nova/modificada)
        mock_obsidian.list_all_notes = AsyncMock(return_value=["Nota1.md", "Nota2.md"])

        nota1_text = "Texto idêntico da nota 1"
        nota2_text = "Texto novo da nota 2"
        hash1 = hashlib.sha256(f"Título: Nota1\nConteúdo: {nota1_text}".encode("utf-8")).hexdigest()

        async def fake_get_content(path):
            if "Nota1.md" in path:
                return nota1_text
            if "Nota2.md" in path:
                return nota2_text
            return ""

        async def fake_get_meta(path):
            title = "Nota1" if "Nota1" in path else "Nota2"
            return {"title": title, "folder": "Inbox"}

        mock_obsidian.get_note_content = AsyncMock(side_effect=fake_get_content)
        mock_obsidian.get_note_metadata = AsyncMock(side_effect=fake_get_meta)

        # No Qdrant já temos Nota1 (com hash idêntico) e Antiga.md (que foi deletada do repo)
        mock_vdb = AsyncMock()
        mock_vdb.get_indexed_metadata_map = AsyncMock(return_value={
            "Nota1.md": hash1,
            "Antiga.md": "hash_antigo"
        })
        mock_vdb.delete_by_path = AsyncMock(return_value=True)
        mock_vdb.upsert_documents = AsyncMock()

        service = KnowledgeDomainService(obsidian_service=mock_obsidian, vector_db_service=mock_vdb)
        result = await service.sync_knowledge()

        self.assertTrue(result.success)
        # Nota1.md foi pulada (unchanged=1)
        self.assertEqual(result.data["unchanged"], 1)
        # Nota2.md foi atualizada (updated=1)
        self.assertEqual(result.data["updated"], 1)
        # Antiga.md foi removida (deleted=1)
        self.assertEqual(result.data["deleted"], 1)
        mock_vdb.delete_by_path.assert_called_once_with("Antiga.md")

        # Upsert chamado apenas com Nota2.md!
        mock_vdb.upsert_documents.assert_called_once()
        upserted_texts = mock_vdb.upsert_documents.call_args[1]["texts"]
        self.assertEqual(len(upserted_texts), 1)
        self.assertIn("Nota2", upserted_texts[0])


if __name__ == "__main__":
    unittest.main()
