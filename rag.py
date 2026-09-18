import numpy as np
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer, CrossEncoder
from rank_bm25 import BM25Okapi
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

DOCUMENTS = [
    {
        "id": 1,
        "title": "MySQL Connection Refused (10061)",
        "content": "Error 10061 target machine actively refused it indicates the MySQL daemon is not running on port 3306 or firewall blocks traffic. Remediate with: Start-Service mysql or check netstat -ano | findstr 3306."
    },
    {
        "id": 2,
        "title": "Distributed Transaction Deadlock",
        "content": "Deadlock in distributed transaction workers indicates lock wait timeout during sync. Remediate by inspecting long-running locks with Get-Process or examining innodb engine logs."
    },
    {
        "id": 3,
        "title": "Out of Memory (OOM) Killer Invocation",
        "content": "Kernel OOM occurs when total system memory allocation exceeds swap limits. Inspect top memory consumers using Get-Process sorted by WS/PM memory."
    },
    {
        "id": 4,
        "title": "Network Port Exhaustion",
        "content": "TCP port exhaustion occurs when sockets linger in TIME_WAIT. Remediate by inspecting active socket connections using Get-NetTCPConnection."
    }
]

class HybridRAG:
    def __init__(self):
        print("Initializing Dense Embedder & Cross-Encoder Reranker...")
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        # Lightweight, high-precision reranker
        self.reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        
        self.qdrant = QdrantClient(":memory:")
        self.collection_name = "incident_runbooks"
        self.docs = DOCUMENTS
        
        tokenized_corpus = [doc["content"].lower().split() for doc in self.docs]
        self.bm25 = BM25Okapi(tokenized_corpus)
        self._build_vector_index()

    def _build_vector_index(self):
        self.qdrant.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )
        
        texts = [f"{d['title']}: {d['content']}" for d in self.docs]
        embeddings = self.embedder.encode(texts)
        
        points = [
            PointStruct(
                id=doc["id"],
                vector=embeddings[idx].tolist(),
                payload=doc
            )
            for idx, doc in enumerate(self.docs)
        ]
        self.qdrant.upsert(collection_name=self.collection_name, points=points)

    def retrieve_and_rerank(self, query: str, candidate_pool: int = 3, top_k: int = 1) -> List[Dict[str, Any]]:
        """Hybrid Search (BM25 + Qdrant) -> Cross-Encoder Re-scoring"""
        # 1. BM25 Search
        query_tokens = query.lower().split()
        bm25_scores = self.bm25.get_scores(query_tokens)
        bm25_ranked = np.argsort(bm25_scores)[::-1]

        # 2. Qdrant Dense Vector Search
        query_vector = self.embedder.encode(query).tolist()
        search_result = self.qdrant.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=len(self.docs)
        )
        vector_hits = search_result.points

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_scores: Dict[int, float] = {}
        for rank, hit in enumerate(vector_hits):
            doc_id = hit.payload["id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (60 + rank + 1))
            
        for rank, doc_idx in enumerate(bm25_ranked):
            doc_id = self.docs[doc_idx]["id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (60 + rank + 1))

        # Select top candidates for reranking
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:candidate_pool]
        candidates = [doc for doc in self.docs if doc["id"] in sorted_ids]

        # 4. Cross-Encoder Precise Rerank
        pairs = [[query, doc["content"]] for doc in candidates]
        scores = self.reranker.predict(pairs)
        
        # Sort candidates by reranker score
        reranked_indices = np.argsort(scores)[::-1]
        final_docs = [candidates[idx] for idx in reranked_indices[:top_k]]
        return final_docs