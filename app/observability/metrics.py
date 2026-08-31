"""
AI Capability Demo — Metrics Registry
Prometheus instrumentation stubs for app request rates, error rates, and RAG quality indicators.
AGENTS.md Section 2 & 4
"""

import logging
from typing import Dict, Any
from prometheus_client import Counter, Gauge, Histogram, Summary

logger = logging.getLogger(__name__)

# ── PROMETHEUS METRICS REGISTRY ──────────────────────────────────────────────

# General HTTP/App Metrics
APP_REQUEST_COUNT = Counter("app_requests_total", "Total requests received by the Streamlit application")
APP_ERROR_COUNT = Counter("app_errors_total", "Total system/LLM errors detected")
APP_LATENCY = Histogram("app_latency_seconds", "Streamlit UI response latencies")

# LLM & Token Metrics
LLM_CALL_COUNT = Counter("llm_calls_total", "Total LLM API requests executed", ["model", "use_case"])
TOKEN_SPEND_COUNTER = Counter("llm_spend_usd_total", "Total cost in USD spent on LLM APIs")
LLM_LATENCY_SUMMARY = Summary("llm_latency_ms", "LLM call duration in milliseconds", ["model"])

# RAG Quality Metrics
RAG_RETRIEVAL_QUALITY = Gauge("rag_retrieval_quality_score", "RAG retrieval confidence or relevance rating", ["use_case"])
RAG_RETRIEVED_CHUNKS = Counter("rag_chunks_retrieved_total", "Total database vector search matches retrieved")

# Use Case KPI Readiness Indices
UC_READINESS_SCORE = Gauge("uc_readiness_percentage", "AI Capability readiness index per use-case", ["use_case"])

class MetricsManager:
    """Manages recording application instrumentation to Prometheus."""
    
    @staticmethod
    def record_request():
        """Increment application request count."""
        try:
            APP_REQUEST_COUNT.inc()
        except Exception:
            pass

    @staticmethod
    def record_error():
        """Increment system errors count."""
        try:
            APP_ERROR_COUNT.inc()
        except Exception:
            pass

    @staticmethod
    def record_llm_call(model: str, use_case: str, cost: float, duration_ms: float):
        """Record details of a successful LLM call."""
        try:
            LLM_CALL_COUNT.labels(model=model, use_case=use_case).inc()
            TOKEN_SPEND_COUNTER.inc(cost)
            LLM_LATENCY_SUMMARY.labels(model=model).observe(duration_ms)
        except Exception:
            pass

    @staticmethod
    def record_rag_score(use_case: str, score: float):
        """Update active RAG retrieval scores."""
        try:
            RAG_RETRIEVAL_QUALITY.labels(use_case=use_case).set(score)
            RAG_RETRIEVED_CHUNKS.inc(1)
        except Exception:
            pass

    @staticmethod
    def update_readiness(use_case: str, score: float):
        """Publish active capability score."""
        try:
            UC_READINESS_SCORE.labels(use_case=use_case).set(score)
        except Exception:
            pass
