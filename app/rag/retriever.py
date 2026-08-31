"""
RAGRetriever — Hybrid semantic + keyword retrieval from FAISS.

Two retrieval paths are executed in parallel:
1. **Semantic**: Embeds the query via OpenAI ``text-embedding-3-small`` (or mock fallback) and
   performs ANN search in FAISSIndexManager.
2. **Keyword (BM25-style)**: Searches the stored text payloads using a simple TF-IDF / BM25
   approximation in FAISSIndexManager.

Results are merged via **Reciprocal Rank Fusion (RRF)** and returned as
a ranked list of ``{text, score, metadata}`` dicts. The ``build_context``
helper truncates results to a token budget for direct LLM injection.
"""
from __future__ import annotations

import logging
import math
import os
import re
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import numpy as np
import hashlib

from dotenv import load_dotenv
from app.rag.indexes import FAISSIndexManager

# override=False: see app/rag/ingestor.py — this module loads after
# SettingsStore has already applied UI-configured overrides to os.environ.
load_dotenv(override=False)

logger = logging.getLogger(__name__)

_EMBED_MODEL = "text-embedding-3-small"


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


class RAGRetriever:
    """Hybrid semantic + keyword retriever backed by FAISSIndexManager.

    Usage::

        retriever = RAGRetriever(faiss_manager=my_manager)
        results = retriever.retrieve(
            query="Critical CVEs on internet-exposed assets",
            collection="ctem_vulnerabilities",
            top_k=50,
        )
        context = retriever.build_context(results, max_tokens=25000)
    """

    RRF_K: int = 60  # Reciprocal Rank Fusion constant

    def __init__(
        self,
        faiss_manager: Optional[FAISSIndexManager] = None,
        embedder: Optional[Callable[[str], List[float]]] = None,
        faiss_client: Optional[Any] = None,  # Kept for backward compatibility
    ) -> None:
        """Initialise the retriever.

        Args:
            faiss_manager: An initialised ``FAISSIndexManager`` instance.
            embedder: Optional callable that takes a query string and returns
                an embedding vector. If ``None``, uses OpenAI.
        """
        self.manager = faiss_manager or FAISSIndexManager()
        self._embedder = embedder
        self._openai_client: Optional[Any] = None
        self._openai_client_key: Optional[str] = None

    @property
    def _openai_api_key(self) -> str:
        # Read fresh, not cached at construction — this instance lives for the
        # whole process, so a key saved later via Settings must take effect
        # without a restart.
        return os.getenv("OPENAI_API_KEY", "")

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    def _get_openai_client(self) -> Any:
        current_key = self._openai_api_key
        # Rebuild the cached client if the key changed since it was built,
        # so a Settings-page key update doesn't keep using a stale client.
        if self._openai_client is None or self._openai_client_key != current_key:
            import openai

            # Bounded timeout — this call happens inside RAGService.query()
            # while holding its shared lock; an unbounded hang here would
            # block every subsequent Copilot request, not just this one.
            self._openai_client = openai.OpenAI(api_key=current_key, timeout=20.0, max_retries=1)
            self._openai_client_key = current_key
        return self._openai_client

    def _embed_query(self, query: str) -> List[float]:
        """Embed a single query string using OpenAI or offline deterministic mock."""
        if self._embedder is not None:
            return self._embedder(query)
        
        if self._openai_api_key:
            try:
                client = self._get_openai_client()
                resp = client.embeddings.create(model=_EMBED_MODEL, input=[query])
                return resp.data[0].embedding
            except Exception as exc:
                logger.warning("OpenAI embedding API failed. Falling back to offline mock. Error: %s", exc)

        # Generate deterministic 1536-dimensional mock query vector
        hasher = hashlib.md5(query.encode("utf-8"))
        seed_val = int(hasher.hexdigest(), 16) % (2**32 - 1)
        rng = np.random.default_rng(seed_val)
        vec = rng.normal(0, 1, 1536)
        norm = np.linalg.norm(vec)
        vec = (vec / norm if norm > 0 else vec).tolist()
        return vec

    # ------------------------------------------------------------------
    # Public retrieve
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        collection: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 50,
    ) -> List[Dict[str, Any]]:
        """Hybrid retrieval: semantic + keyword, merged via RRF using FAISS.

        Args:
            query: Natural-language query string.
            collection: FAISS Index name.
            filters: Optional metadata filters (``{field: value}``).
            top_k: Maximum number of results to return.

        Returns:
            List of result dicts sorted by fused relevance score.
            Each dict has keys: ``text``, ``score``, ``rrf_score``,
            ``metadata``, ``source``, ``id``.
        """
        logger.info(
            "Hybrid retrieve (FAISS): query='%s' collection='%s' top_k=%d",
            query[:80],
            collection,
            top_k,
        )

        # 1. Embed query
        query_embedding = self._embed_query(query)

        # 2. Search FAISS index manager (RRF hybrid search)
        search_k = top_k * 4 if filters else top_k
        raw_results = self.manager.hybrid_search(
            index_name=collection,
            query=query,
            query_embedding=query_embedding,
            top_k=search_k,
        )

        # 3. Apply post-filters on metadata if required
        filtered_results = []
        for doc in raw_results:
            meta = doc.get("metadata", {})
            match = True
            if filters:
                for k, v in filters.items():
                    val = meta.get(k, doc.get(k))
                    if val != v:
                        match = False
                        break
            if match:
                filtered_results.append(doc)

        logger.info(
            "Retrieved %d hybrid results for query in '%s' (after filters: %d).",
            len(raw_results),
            collection,
            len(filtered_results),
        )

        return filtered_results[:top_k]

    # ------------------------------------------------------------------
    # Context builder
    # ------------------------------------------------------------------

    def build_context(
        self,
        results: List[Dict[str, Any]],
        max_tokens: int = 25_000,
    ) -> str:
        """Build a context string from retrieval results for LLM injection.

        Concatenates result texts in relevance order until the token
        budget is exhausted.

        Args:
            results: Output from :meth:`retrieve`.
            max_tokens: Maximum approximate token count.

        Returns:
            A single string suitable for inclusion in an LLM prompt.
        """
        if not results:
            return ""

        parts: List[str] = []
        total_tokens = 0

        for i, doc in enumerate(results):
            text = doc.get("text", "")
            tokens = _estimate_tokens(text)
            if total_tokens + tokens > max_tokens:
                logger.info(
                    "Context truncated at %d/%d results (%d tokens).",
                    i,
                    len(results),
                    total_tokens,
                )
                break
            parts.append(text)
            total_tokens += tokens

        return "\n\n---\n\n".join(parts)

    # ------------------------------------------------------------------
    # Multi-collection retrieval
    # ------------------------------------------------------------------

    def retrieve_across_collections(
        self,
        query: str,
        collections: Sequence[str],
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve from multiple FAISS collections and merge all results.

        Args:
            query: Natural-language query string.
            collections: List of FAISS collection names.
            filters: Optional metadata filters applied to all collections.
            top_k: Maximum total results after merge.

        Returns:
            Merged result list sorted by RRF score.
        """
        all_results = []
        for coll in collections:
            results = self.retrieve(query, coll, filters, top_k)
            for doc in results:
                if "metadata" not in doc:
                    doc["metadata"] = {}
                doc["metadata"]["collection"] = coll
            all_results.extend(results)

        # De-duplicate and sort by fused relevance (highest rrf_score/score first)
        all_results.sort(key=lambda x: x.get("rrf_score", x.get("score", 0.0)), reverse=True)

        seen_texts = set()
        deduped = []
        for doc in all_results:
            t = doc.get("text", "")
            if t not in seen_texts:
                seen_texts.add(t)
                deduped.append(doc)

        return deduped[:top_k]

