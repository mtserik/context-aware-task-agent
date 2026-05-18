import os
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from langchain_openai import OpenAIEmbeddings

class VectorDBService:
    """
    Serviço responsável pela interface com o banco de dados vetorial Qdrant.
    Em Data Science, esta é a nossa camada de Recuperação (Retrieval).
    """
    def __init__(self):
        # O URL virá do docker-compose ou do .env local
        self.client = QdrantClient(
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            api_key=os.getenv("QDRANT_API_KEY")
        )
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.collection_name = "maeve_knowledge"
        self._ensure_collection()

    def _ensure_collection(self):
        """Garante que a coleção existe no Qdrant."""
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)
        
        if not exists:
            # text-embedding-3-small tem 1536 dimensões
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )

    async def upsert_documents(self, texts: list[str], metadatas: list[dict] = None):
        """Transforma textos em vetores e armazena no Qdrant."""
        if not texts:
            return

        embeddings = self.embeddings.embed_documents(texts)
        points = []
        
        for i, (text, vector) in enumerate(zip(texts, embeddings)):
            metadata = metadatas[i] if metadatas else {}
            metadata["content"] = text
            points.append(PointStruct(
                id=hash(text + str(i)) % (10**10), # ID simples para exemplo
                vector=vector,
                payload=metadata
            ))
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

    async def search_context(self, query: str, limit: int = 3):
        """
        Realiza uma busca semântica para encontrar contextos relevantes.
        Isso é o 'R' do RAG (Retrieval-Augmented Generation).
        """
        query_vector = self.embeddings.embed_query(query)
        
        hits = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit
        )
        
        return [hit.payload.get("content", "") for hit in hits]