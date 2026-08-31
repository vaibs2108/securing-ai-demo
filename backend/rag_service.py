"""
Securing AI — RAG service for the Copilot.
Wraps app/rag/{indexes,ingestor,retriever}.py (a fully-built hybrid FAISS +
BM25 engine that was previously unwired) with:
  - background ingestion of the 16 synthetic datasets at startup (capped per
    dataset so a restart doesn't re-embed thousands of rows every time)
  - file-upload chunking + embedding into a dedicated "uploads" collection
  - a single query entry point that retrieves across every collection

Locking note: FAISS's IndexFlatIP is not safe for concurrent add()/search()
from different threads, so every mutation/read of `self.manager` goes through
`self._lock`. Critically, the lock is held only around the FAISS add/search
calls themselves (fast, local, milliseconds) — never around the OpenAI
embedding network calls (seconds, occasionally much slower). An earlier
version locked the whole ingest-a-batch call, which meant one slow/stalled
embedding request during startup indexing blocked every Copilot query behind
it for as long as that request took. Embedding calls also carry an explicit
bounded timeout (app/rag/ingestor.py, app/rag/retriever.py) so a stalled
request fails fast instead of hanging indefinitely either way.
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.rag.indexes import FAISSIndexManager
from app.rag.ingestor import RAGIngestor
from app.rag.retriever import RAGRetriever
from app.rag.collections import DATASET_COLLECTIONS

logger = logging.getLogger(__name__)

# Cap rows embedded per dataset — keeps startup ingestion to a few dozen
# batched embedding calls (seconds, fractions of a cent) instead of
# re-embedding thousands of rows on every process restart.
_MAX_ROWS_PER_DATASET = 300
_EMBED_BATCH_SIZE = 100
_CHUNK_SIZE = 1000
_CHUNK_OVERLAP = 150

# Columns computed relative to datetime.now() at generation time (see
# app/data/generator.py) — every one of these differs on every process
# restart regardless of the fixed seed, since the seed only controls the
# *random offset* (np.random.randint(...) days ago), not the wall-clock
# anchor. Verified empirically: two back-to-back generate_all() calls in
# separate processes produced identical output for every column EXCEPT
# these. Excluded from the cache fingerprint so a restart with otherwise
# byte-identical data still hits the cache — this only affects cache
# invalidation, not what actually gets embedded (the real, slightly
# time-shifted values are still embedded in the RAG text as normal). If
# generator.py adds a new datetime.now()-derived column, add it here too,
# or the cache will silently never hit for that dataset again.
_VOLATILE_COLUMNS: Dict[str, List[str]] = {
    "ai_agent_inventory": ["first_seen_date"],
    "model_data_lineage": ["last_lineage_scan"],
    "agent_risk_register": ["last_assessed"],
    "guardrail_policies": ["created_date"],
    "guardrail_events": ["timestamp"],
    "tool_access_map": ["last_reviewed"],
    "secrets_exposure_scan": ["discovered_date"],
    "agent_behavior_telemetry": ["timestamp"],
    "incident_queue": ["detected_at"],
    "containment_actions": ["timestamp"],
    "config_snapshots": ["created_at"],
    "rollback_events": ["timestamp"],
    "guardrail_update_log": ["deployed_at"],
}

# Disk cache for the dataset embeddings — lives alongside the other SQLite
# files in data/. Historically the synthetic datasets were generated with a
# fixed seed, so this cache reliably hit across restarts; datasets are now
# regenerated with a fresh random seed every process start (backend/state.py)
# so the content-fingerprint check below will normally miss on every restart
# — that's an accepted tradeoff for genuinely dynamic demo data, not a bug.
# The cache is kept because it still helps in-place (e.g. hot-reload without
# a full process restart) and costs nothing when it misses. Bump
# _CACHE_VERSION to force-invalidate all caches after a format change (e.g.
# a different row-to-text template).
_CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "rag_cache"
_CACHE_VERSION = 1


def _chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> List[str]:
    """Simple fixed-size character chunker with overlap. Good enough for the
    demo's document sizes (policies, logs, code) — no dependency on a
    tokenizer-aware splitter."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = end - overlap
    return chunks


def _row_to_text(row_dict: Dict[str, Any], collection_name: str) -> str:
    """Mirrors RAGIngestor.ingest_dataframe's row-to-text format exactly, so
    chunks embedded here read identically to ones the ingestor embeds itself."""
    text = f"Security data record in collection {collection_name}.\n"
    for col, val in row_dict.items():
        text += f"{col}: {val}\n"
    return text


def _row_payload(row_dict: Dict[str, Any], text: str, extra: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"text_content": text, **extra}
    for col, val in row_dict.items():
        if isinstance(val, (dict, list)):
            payload[col] = str(val)
        elif pd.isna(val):
            payload[col] = None
        else:
            payload[col] = val
    return payload


@dataclass
class UploadedDoc:
    filename: str
    chunks: int
    chars: int
    uploaded_at: float = field(default_factory=time.time)


class RAGService:
    def __init__(self) -> None:
        self.manager = FAISSIndexManager()
        self.ingestor = RAGIngestor(faiss_manager=self.manager)
        self.retriever = RAGRetriever(faiss_manager=self.manager)
        self.uploads: List[UploadedDoc] = []
        self._lock = threading.Lock()
        self.dataset_status: Dict[str, str] = {name: "pending" for name in DATASET_COLLECTIONS}
        self.ready = False
        self.building = False
        self.error: Optional[str] = None

    # ── Dataset ingestion (runs in a background thread) ────────────────

    def build_dataset_index_async(self, datasets: Dict[str, pd.DataFrame]) -> None:
        thread = threading.Thread(target=self._build_dataset_index, args=(datasets,), daemon=True)
        thread.start()

    def _build_dataset_index(self, datasets: Dict[str, pd.DataFrame]) -> None:
        self.building = True
        try:
            samples: Dict[str, pd.DataFrame] = {}
            for name in DATASET_COLLECTIONS:
                df = datasets.get(name)
                if df is None or df.empty:
                    self.dataset_status[name] = "empty"
                    continue
                samples[name] = df if len(df) <= _MAX_ROWS_PER_DATASET else df.sample(
                    n=_MAX_ROWS_PER_DATASET, random_state=42
                )

            try:
                fingerprint: Optional[str] = self._fingerprint(samples)
            except Exception:
                logger.exception("RAG fingerprinting failed — proceeding without disk caching for this run")
                fingerprint = None

            if fingerprint and self._load_cache(fingerprint):
                logger.info("RAG cache hit (fingerprint=%s) — skipped re-embedding %d datasets",
                            fingerprint[:12], len(samples))
                self.ready = True
                return

            logger.info("RAG cache miss (fingerprint=%s) — embedding %d datasets",
                        fingerprint[:12] if fingerprint else "n/a", len(samples))
            for name, sample in samples.items():
                try:
                    count = self._ingest_dataframe_unlocked_embed(sample, name)
                    self.dataset_status[name] = f"indexed:{count}"
                except Exception as exc:
                    logger.exception("Failed to index dataset %s into RAG store", name)
                    self.dataset_status[name] = f"error:{exc}"
            self.ready = True

            if fingerprint and not any(v.startswith("error") for v in self.dataset_status.values()):
                self._save_cache(fingerprint)
            else:
                logger.warning("Skipping RAG cache save — one or more datasets failed to index")
        except Exception as exc:
            self.error = str(exc)
            logger.exception("RAG dataset indexing failed")
        finally:
            self.building = False

    # ── Disk cache ───────────────────────────────────────────────────────

    @staticmethod
    def _fingerprint(samples: Dict[str, pd.DataFrame]) -> str:
        """Deterministic fingerprint of exactly what would be embedded, minus
        the datetime.now()-relative columns (_VOLATILE_COLUMNS) that differ
        on every restart regardless of the fixed seed. Stable across restarts
        unless the generator's non-timestamp output, the row cap, or the
        cache format itself changes — any of which should (and will)
        invalidate the cache."""
        # Note: pd.util.hash_pandas_object() can't hash columns containing
        # Python lists (e.g. agent_risk_register.risk_factors,
        # soar_playbooks.steps), which several of these datasets have — so
        # this hashes each dataframe's own JSON serialisation instead, which
        # already handles list-valued cells correctly (same code path
        # backend/utils.py's df_to_records uses for API responses).
        hasher = hashlib.sha256()
        hasher.update(str(_CACHE_VERSION).encode())
        hasher.update(str(_MAX_ROWS_PER_DATASET).encode())
        for name in sorted(samples):
            df = samples[name]
            volatile = _VOLATILE_COLUMNS.get(name, [])
            stable_df = df.drop(columns=[c for c in volatile if c in df.columns]) if volatile else df
            hasher.update(name.encode())
            hasher.update(str(stable_df.shape).encode())
            hasher.update(stable_df.to_json(orient="records", default_handler=str).encode())
        return hasher.hexdigest()

    def _load_cache(self, fingerprint: str) -> bool:
        manifest_path = _CACHE_DIR / "manifest.json"
        if not manifest_path.exists():
            return False
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            return False
        if manifest.get("fingerprint") != fingerprint:
            return False

        import faiss
        loaded: Dict[str, Any] = {}
        try:
            for name in DATASET_COLLECTIONS:
                idx_path = _CACHE_DIR / f"{name}.faiss"
                doc_path = _CACHE_DIR / f"{name}.pkl"
                if not idx_path.exists() or not doc_path.exists():
                    return False  # partial/corrupt cache — rebuild from scratch
                loaded[name] = (faiss.read_index(str(idx_path)), pickle.loads(doc_path.read_bytes()))
        except Exception:
            logger.exception("Failed to load RAG cache — rebuilding from scratch")
            return False

        with self._lock:
            for name, (index, doc_store) in loaded.items():
                self.manager.indexes[name] = index
                self.manager.doc_stores[name] = doc_store
                self.dataset_status[name] = f"cached:{index.ntotal}"
        return True

    def _save_cache(self, fingerprint: str) -> None:
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            import faiss
            with self._lock:
                for name in DATASET_COLLECTIONS:
                    if name not in self.manager.indexes:
                        continue
                    faiss.write_index(self.manager.indexes[name], str(_CACHE_DIR / f"{name}.faiss"))
                    (_CACHE_DIR / f"{name}.pkl").write_bytes(pickle.dumps(self.manager.doc_stores[name]))
            (_CACHE_DIR / "manifest.json").write_text(
                json.dumps({"fingerprint": fingerprint, "saved_at": time.time()})
            )
            logger.info("Saved RAG cache to %s (fingerprint=%s)", _CACHE_DIR, fingerprint[:12])
        except Exception:
            logger.exception("Failed to save RAG cache — will re-embed next restart")

    def _ingest_dataframe_unlocked_embed(self, df: pd.DataFrame, collection_name: str) -> int:
        """Same behaviour as RAGIngestor.ingest_dataframe, but embeds each
        batch OUTSIDE self._lock and only takes the lock around manager.add()."""
        rows = list(df.iterrows())
        count = 0
        for i in range(0, len(rows), _EMBED_BATCH_SIZE):
            batch = rows[i:i + _EMBED_BATCH_SIZE]
            texts = [_row_to_text(row.to_dict(), collection_name) for _, row in batch]
            payloads = [
                _row_payload(row.to_dict(), text, {"data_source": "synthetic", "row_index": idx})
                for (idx, row), text in zip(batch, texts)
            ]
            embeddings = self.ingestor._embed_texts(texts)  # network call — unlocked
            with self._lock:
                self.manager.add(index_name=collection_name, texts=texts, metadata=payloads, embeddings=embeddings)
            count += len(texts)
        return count

    # ── Uploads ──────────────────────────────────────────────────────────

    def ingest_upload(self, filename: str, text: str) -> UploadedDoc:
        chunks = _chunk_text(text)
        embeddings = self.ingestor._embed_texts(chunks)  # network call — unlocked
        payloads = [{"text_content": c, "chunk_index": i, "source": filename} for i, c in enumerate(chunks)]
        with self._lock:
            self.manager.add(index_name="uploads", texts=chunks, metadata=payloads, embeddings=embeddings)
            doc = UploadedDoc(filename=filename, chunks=len(chunks), chars=len(text))
            self.uploads.append(doc)
        return doc

    def clear_uploads(self) -> None:
        with self._lock:
            import faiss
            self.manager.indexes["uploads"] = faiss.IndexFlatIP(1536)
            self.manager.doc_stores["uploads"] = []
            self.uploads = []

    # ── Query ────────────────────────────────────────────────────────────

    def query(self, question: str, top_k: int = 8) -> List[Dict[str, Any]]:
        collections = DATASET_COLLECTIONS + ["uploads"]
        query_embedding = self.retriever._embed_query(question)  # network call — unlocked
        with self._lock:
            all_results = []
            for coll in collections:
                results = self.manager.hybrid_search(coll, question, query_embedding, top_k=top_k)
                for doc in results:
                    doc.setdefault("metadata", {})["collection"] = coll
                all_results.extend(results)
        all_results.sort(key=lambda x: x.get("rrf_score", x.get("score", 0.0)), reverse=True)
        seen, deduped = set(), []
        for doc in all_results:
            t = doc.get("text", "")
            if t not in seen:
                seen.add(t)
                deduped.append(doc)
        return deduped[:top_k]

    def build_context(self, results: List[Dict[str, Any]], max_tokens: int = 6000) -> str:
        return self.retriever.build_context(results, max_tokens=max_tokens)

    # ── Status ───────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        vector_counts = {
            name: self.manager.indexes[name].ntotal
            for name in DATASET_COLLECTIONS
            if name in self.manager.indexes
        }
        return {
            "ready": self.ready,
            "building": self.building,
            "error": self.error,
            "dataset_status": self.dataset_status,
            "dataset_vector_counts": vector_counts,
            "total_dataset_vectors": sum(vector_counts.values()),
            "upload_vector_count": self.manager.indexes["uploads"].ntotal if "uploads" in self.manager.indexes else 0,
            "uploads": [
                {"filename": d.filename, "chunks": d.chunks, "chars": d.chars, "uploaded_at": d.uploaded_at}
                for d in self.uploads
            ],
        }
