"""
FAISS Collections Reference — one collection per Securing AI dataset, plus
"uploads" for the Copilot's user-uploaded document memory.
Mirrors app/rag/indexes.py's FAISSIndexManager.INDEXES exactly — kept as a
separate reference module for readability. AGENTS.md Section 28.7.
"""
from __future__ import annotations

from typing import Dict, List, Any

FAISS_COLLECTIONS: Dict[str, Dict[str, Any]] = {
    "ai_agent_inventory": {"vector_size": 1536, "distance": "Cosine"},
    "model_data_lineage": {"vector_size": 1536, "distance": "Cosine"},
    "agent_risk_register": {"vector_size": 1536, "distance": "Cosine"},
    "guardrail_policies": {"vector_size": 1536, "distance": "Cosine"},
    "guardrail_events": {"vector_size": 1536, "distance": "Cosine"},
    "tool_access_map": {"vector_size": 1536, "distance": "Cosine"},
    "secrets_exposure_scan": {"vector_size": 1536, "distance": "Cosine"},
    "adversarial_prompt_corpus": {"vector_size": 1536, "distance": "Cosine"},
    "agent_behavior_telemetry": {"vector_size": 1536, "distance": "Cosine"},
    "redteam_campaign_results": {"vector_size": 1536, "distance": "Cosine"},
    "incident_queue": {"vector_size": 1536, "distance": "Cosine"},
    "containment_actions": {"vector_size": 1536, "distance": "Cosine"},
    "soar_playbooks": {"vector_size": 1536, "distance": "Cosine"},
    "config_snapshots": {"vector_size": 1536, "distance": "Cosine"},
    "rollback_events": {"vector_size": 1536, "distance": "Cosine"},
    "guardrail_update_log": {"vector_size": 1536, "distance": "Cosine"},
    "uploads": {"vector_size": 1536, "distance": "Cosine"},
}

DATASET_COLLECTIONS: List[str] = [k for k in FAISS_COLLECTIONS if k != "uploads"]
