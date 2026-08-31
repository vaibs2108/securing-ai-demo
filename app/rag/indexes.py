"""
FAISS Index Manager — Manages multiple named FAISS indexes in memory.
Each index corresponds to one FAISS index in the production architecture.
AGENTS.md Section 6.2.
"""
from __future__ import annotations

import faiss
import numpy as np
import re
import math
from collections import Counter
from typing import List, Dict, Any, Optional

class FAISSIndexManager:
    """Manages multiple named FAISS indexes in memory.
    
    Each index corresponds to one collection in the production architecture.
    """

    INDEXES = {
        # Identify
        "ai_agent_inventory":     {"vector_size": 1536},
        "model_data_lineage":     {"vector_size": 1536},
        "agent_risk_register":    {"vector_size": 1536},
        # Protect
        "guardrail_policies":     {"vector_size": 1536},
        "guardrail_events":       {"vector_size": 1536},
        "tool_access_map":        {"vector_size": 1536},
        "secrets_exposure_scan":  {"vector_size": 1536},
        # Detect
        "adversarial_prompt_corpus":  {"vector_size": 1536},
        "agent_behavior_telemetry":   {"vector_size": 1536},
        "redteam_campaign_results":   {"vector_size": 1536},
        # Respond
        "incident_queue":         {"vector_size": 1536},
        "containment_actions":    {"vector_size": 1536},
        "soar_playbooks":         {"vector_size": 1536},
        # Recover
        "config_snapshots":       {"vector_size": 1536},
        "rollback_events":        {"vector_size": 1536},
        "guardrail_update_log":   {"vector_size": 1536},
        # User-uploaded documents (Section 28.7 — Copilot "AI Memory Bank")
        "uploads":                {"vector_size": 1536},
    }

    def __init__(self) -> None:
        self.indexes: dict[str, faiss.IndexFlatIP] = {}
        self.doc_stores: dict[str, list[dict]] = {}  # parallel list of metadata dicts
        self._init_all()

    def _init_all(self) -> None:
        """Initialise all indexes."""
        for name, schema in self.INDEXES.items():
            self.indexes[name] = faiss.IndexFlatIP(schema["vector_size"])
            self.doc_stores[name] = []

    def add(self, index_name: str, texts: list[str],
            metadata: list[dict], embeddings: list[list[float]]) -> None:
        """Add vectors + metadata to a named index."""
        if index_name not in self.indexes:
            raise ValueError(f"Index '{index_name}' not defined in FAISSIndexManager.")
        if not texts:
            return
        
        # Norm-normalize embeddings to make dot product equivalent to cosine similarity
        vectors = np.array(embeddings, dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        normalized_vectors = np.where(norms > 0, vectors / norms, vectors)
        
        self.indexes[index_name].add(normalized_vectors)
        
        # Store parallel metadata. Ensure each metadata dict has a 'text' key populated with text
        for text, meta in zip(texts, metadata):
            doc = meta.copy()
            doc["text"] = text
            self.doc_stores[index_name].append(doc)

    def search(self, index_name: str, query_embedding: list[float],
               top_k: int = 50) -> list[dict]:
        """Semantic search on named index. Returns metadata dicts."""
        if index_name not in self.indexes or self.indexes[index_name].ntotal == 0:
            return []
            
        q_vec = np.array([query_embedding], dtype=np.float32)
        q_norm = np.linalg.norm(q_vec, axis=1, keepdims=True)
        if q_norm[0, 0] > 0:
            q_vec = q_vec / q_norm
            
        limit = min(top_k, self.indexes[index_name].ntotal)
        scores, indices = self.indexes[index_name].search(q_vec, limit)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.doc_stores[index_name]):
                continue
            doc = self.doc_stores[index_name][idx]
            results.append({
                "id": str(idx),
                "text": doc.get("text", ""),
                "score": float(score),
                "metadata": {k: v for k, v in doc.items() if k != "text"},
                "source": "semantic"
            })
        return results

    @staticmethod
    def _tokenise(text: str) -> list[str]:
        """Simple whitespace + punctuation tokeniser (lowercased)."""
        return re.findall(r"[a-z0-9]+", text.lower())

    @classmethod
    def _bm25_score(
        cls,
        query_tokens: list[str],
        doc_tokens: list[str],
        avg_dl: float,
        doc_count: int,
        df_map: dict[str, int],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> float:
        """Compute an Okapi BM25 score for a single document."""
        dl = len(doc_tokens)
        doc_tf = Counter(doc_tokens)
        score = 0.0
        for qt in query_tokens:
            tf = doc_tf.get(qt, 0)
            if tf == 0:
                continue
            df = df_map.get(qt, 0)
            idf = math.log(
                (doc_count - df + 0.5) / (df + 0.5) + 1.0
            )
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1.0 - b + b * (dl / max(avg_dl, 1.0)))
            score += idf * (numerator / denominator)
        return score

    def bm25_search(self, index_name: str, query: str,
                    top_k: int = 20) -> list[dict]:
        """Keyword search using BM25 on stored text. Returns metadata dicts."""
        if index_name not in self.doc_stores or not self.doc_stores[index_name]:
            return []
            
        query_tokens = self._tokenise(query)
        if not query_tokens:
            return []
            
        docs = self.doc_stores[index_name]
        all_doc_tokens = [self._tokenise(doc.get("text", "")) for doc in docs]
        doc_count = len(docs)
        avg_dl = sum(len(dt) for dt in all_doc_tokens) / max(doc_count, 1)
        
        df_map = {}
        for qt in set(query_tokens):
            df_map[qt] = sum(1 for dt in all_doc_tokens if qt in dt)
            
        scored = []
        for idx, doc_tokens in enumerate(all_doc_tokens):
            s = self._bm25_score(query_tokens, doc_tokens, avg_dl, doc_count, df_map)
            if s > 0:
                scored.append((s, idx))
                
        scored.sort(key=lambda x: x[0], reverse=True)
        scored = scored[:top_k]
        
        results = []
        for score, idx in scored:
            doc = docs[idx]
            results.append({
                "id": str(idx),
                "text": doc.get("text", ""),
                "score": float(score),
                "metadata": {k: v for k, v in doc.items() if k != "text"},
                "source": "keyword"
            })
        return results

    def hybrid_search(self, index_name: str, query: str,
                      query_embedding: list[float], top_k: int = 50) -> list[dict]:
        """Merge semantic + BM25 results. Deduplicate. Return top_k."""
        # 1. Semantic search
        semantic_results = self.search(index_name, query_embedding, top_k)
        # 2. BM25 search
        bm25_results = self.bm25_search(index_name, query, top_k)
        
        # 3. Reciprocal Rank Fusion (RRF)
        rrf_scores = {}
        id_to_doc = {}
        RRF_K = 60
        
        for rank, doc in enumerate(semantic_results):
            doc_id = doc["id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (RRF_K + rank + 1)
            if doc_id not in id_to_doc:
                id_to_doc[doc_id] = doc
                
        for rank, doc in enumerate(bm25_results):
            doc_id = doc["id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (RRF_K + rank + 1)
            if doc_id not in id_to_doc:
                id_to_doc[doc_id] = doc
                
        # Sort by fused score descending
        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        
        merged = []
        for doc_id, fused_score in ranked[:top_k]:
            doc = id_to_doc[doc_id].copy()
            doc["rrf_score"] = round(fused_score, 6)
            merged.append(doc)
            
        return merged
