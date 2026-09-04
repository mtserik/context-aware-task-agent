import os
import uuid
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
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
        """Garante que a coleção existe no Qdrant."""
        collections = await self.client.get_collections()
        exists = any(c.name == self.collection_name for c in collections.collections)
        
        if not exists:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )

    async def upsert_documents(self, texts: list[str], metadatas: list[dict] = None):
        """Transforma textos em vetores e armazena no Qdrant."""
        if not texts:
            return

        client = await self._get_client()
        embeddings = await self.embeddings.aembed_documents(texts)
        points = []

        for i, (text, vector) in enumerate(zip(texts, embeddings)):
            metadata = metadatas[i] if metadatas else {}
            metadata["content"] = text
            # Garantir que o ID seja estável e determinístico baseado no path/conteúdo
            stable_key = metadata.get("path") or f"doc_{i}_{text[:64]}"
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

    async def search_context(self, query: str, limit: int = 5):
        """
        Realiza uma busca semântica para encontrar contextos relevantes.
        Retorna uma lista de dicionários com conteúdo e metadados.
        Em caso de erro (ex: Qdrant offline), retorna lista vazia com segurança.
        """
        try:
            client = await self._get_client()
            query_vector = await self.embeddings.aembed_query(query)

            response = await client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                with_payload=True
            )

            return [
                {
                    "content": point.payload.get("content", ""),
                    "metadata": {k: v for k, v in point.payload.items() if k != "content"}
                }
                for point in response.points
            ]
        except Exception as e:
            print(f"⚠️ [VectorDB] Falha ao consultar contexto: {e}")
            return []