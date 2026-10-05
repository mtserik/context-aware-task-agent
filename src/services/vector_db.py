import os
import uuid
import hashlib
from typing import Optional, List, Dict, Any
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from langchain_openai import OpenAIEmbeddings

class VectorDBService:
    """
    Serviço responsável pela interface assíncrona com o banco de dados vetorial Qdrant.
    """
    def __init__(self):
        # O URL virá do docker-compose ou do .env local
        # No Docker, o host é 'local-vector-db'
        self.url = os.getenv("QDRANT_URL", "http://localhost:6333")
        self.api_key = os.getenv("QDRANT_API_KEY")
        self.client = None # Inicializado sob demanda ou em setup
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.collection_name = "maeve_knowledge"

    async def _get_client(self) -> AsyncQdrantClient:
        """Retorna o cliente assíncrono, inicializando-o se necessário."""
        if self.client is None:
            self.client = AsyncQdrantClient(
                url=self.url,
                api_key=self.api_key
            )
            await self._ensure_collection()
        return self.client

    async def _ensure_collection(self):
        """Garante que a coleção e seus índices de payload existem no Qdrant."""
        collections = await self.client.get_collections()
        exists = any(c.name == self.collection_name for c in collections.collections)
        
        if not exists:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )
            for field in ["source", "path"]:
                try:
                    await self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name=field,
                        field_schema="keyword",
                    )
                except Exception:
                    pass

    async def upsert_documents(self, texts: list[str], metadatas: list[dict] = None, batch_size: int = 25):
        """
        Transforma textos em vetores e armazena no Qdrant em batches seguros.
        Evita sobrecarga e timeouts na API de embeddings ao processar grandes volumes de notas.
        Gera hash determinístico SHA-256 do conteúdo para sincronização incremental.
        """
        if not texts:
            return

        client = await self._get_client()
        total_items = len(texts)

        for start_idx in range(0, total_items, batch_size):
            end_idx = min(start_idx + batch_size, total_items)
            batch_texts = texts[start_idx:end_idx]
            batch_metas = metadatas[start_idx:end_idx] if metadatas else None

            embeddings = await self.embeddings.aembed_documents(batch_texts)
            points = []

            for i, (text, vector) in enumerate(zip(batch_texts, embeddings)):
                global_idx = start_idx + i
                metadata = dict(batch_metas[i]) if batch_metas else {}
                metadata["content"] = text
                
                # Gera hash SHA-256 do conteúdo para checagem incremental
                content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                metadata["content_hash"] = content_hash

                # Garantir que o ID seja estável e determinístico baseado no path/conteúdo
                stable_key = metadata.get("path") or f"doc_{global_idx}_{text[:64]}"
                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key))

                points.append(PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=metadata
                ))

            await client.upsert(
                collection_name=self.collection_name,
                points=points
            )

    async def search_context(self, query: str, limit: int = 5, score_threshold: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Realiza uma busca semântica para encontrar contextos relevantes.
        Retorna uma lista de dicionários com conteúdo, score de similaridade e metadados.
        Em caso de erro (ex: Qdrant offline), retorna lista vazia com segurança.
        """
        try:
            client = await self._get_client()
            query_vector = await self.embeddings.aembed_query(query)

            query_kwargs: Dict[str, Any] = {
                "collection_name": self.collection_name,
                "query": query_vector,
                "limit": limit,
                "with_payload": True,
            }
            if score_threshold is not None:
                query_kwargs["score_threshold"] = score_threshold

            response = await client.query_points(**query_kwargs)

            return [
                {
                    "content": point.payload.get("content", ""),
                    "score": getattr(point, "score", None),
                    "metadata": {k: v for k, v in point.payload.items() if k != "content"}
                }
                for point in response.points
            ]
        except Exception as e:
            print(f"⚠️ [VectorDB] Falha ao consultar contexto: {e}")
            return []

    async def delete_by_path(self, path: str) -> bool:
        """Remove documentos/pontos associados a um caminho de arquivo no Qdrant."""
        try:
            client = await self._get_client()
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, path))
            # 1. Tenta remoção por ID determinístico
            try:
                await client.delete(
                    collection_name=self.collection_name,
                    points_selector=[point_id]
                )
            except Exception:
                pass
            # 2. Garante remoção por filtro de metadado (caso tenha havido chunks com mesmo path)
            await client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key="path", match=MatchValue(value=path))]
                )
            )
            return True
        except Exception as e:
            print(f"⚠️ [VectorDB] Falha ao deletar documento por path '{path}': {e}")
            return False

    async def get_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Recupera o documento e conteúdo completo do Qdrant usando o path determinístico.
        Permite que o Qdrant seja a fonte canônica e ultra-rápida de leitura para o agente,
        sem necessidade de acessar o sistema de arquivos do servidor.
        """
        try:
            client = await self._get_client()
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, path))
            points = await client.retrieve(
                collection_name=self.collection_name,
                ids=[point_id],
                with_payload=True
            )
            if points and points[0].payload:
                return points[0].payload

            # Fallback por filtro de metadado caso o ID determinístico não bata diretamente
            response, _ = await client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="path", match=MatchValue(value=path))]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False
            )
            if response and response[0].payload:
                return response[0].payload
            return None
        except Exception as e:
            print(f"⚠️ [VectorDB] Erro ao recuperar documento por path '{path}': {e}")
            return None

    async def get_indexed_metadata_map(self) -> Dict[str, str]:
        """
        Retorna um dicionário {path: content_hash} de todas as notas indexadas no Qdrant
        oriundas do Obsidian (source='obsidian').
        Permite sincronização incremental estrita: notas não alteradas são puladas com custo zero.
        """
        try:
            client = await self._get_client()
            path_hash_map: Dict[str, str] = {}
            offset = None

            while True:
                records, next_offset = await client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=Filter(
                        must=[FieldCondition(key="source", match=MatchValue(value="obsidian"))]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=["path", "content_hash"],
                    with_vectors=False
                )
                for record in records:
                    p = record.payload.get("path")
                    h = record.payload.get("content_hash", "")
                    if p:
                        path_hash_map[p] = h

                if next_offset is None:
                    break
                offset = next_offset

            return path_hash_map
        except Exception as e:
            print(f"⚠️ [VectorDB] Erro ao listar metadata do Qdrant: {e}")
            return {}

    async def close(self):
        """Fecha a conexão do cliente Qdrant de forma segura."""
        if self.client:
            try:
                await self.client.close()
            except Exception as e:
                print(f"⚠️ [VectorDB] Erro ao fechar cliente Qdrant: {e}")
            finally:
                self.client = None