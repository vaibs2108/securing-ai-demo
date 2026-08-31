"""
LLM Router — 3-tier model routing with token tracking.

Tier 1: GPT-4o-mini (OpenAI API) — primary for all analysis
Tier 2: Ollama llama3.1:8b (local) — optional, user-selectable
Tier 3: GPT-4o-mini (OpenAI API) — reasoning mode for Detect/Respond

GPT-4o is intentionally kept a "dummy" model name in this build — it's still
recognised by MODEL_TIERS resolution but transparently downgraded to
GPT-4o-mini via _demo_safe() below, so no configuration path (env var, a
stray REASONING_MODEL=gpt-4o, a future settings toggle) can produce a
surprise high-cost call during a demo. Change _DEMO_DUMMY_MODELS to lift this
if real GPT-4o usage is ever wanted.

All calls are tracked via TokenUsageTracker for cost and usage analytics.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Type, Union

import httpx
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.llm.token_tracker import TokenUsageTracker

# override=False: see app/rag/ingestor.py — this module loads after
# SettingsStore has already applied UI-configured overrides to os.environ.
load_dotenv(override=False)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Demo cost guard — see module docstring. gpt-4o remains a valid string
# elsewhere (token_pricing.yaml, an old Settings dropdown option) but is
# never actually sent to the OpenAI API by this router.
_DEMO_DUMMY_MODELS = {"gpt-4o"}
_DEMO_SAFE_MODEL = "gpt-4o-mini"


def _demo_safe(model_name: str) -> str:
    return _DEMO_SAFE_MODEL if model_name in _DEMO_DUMMY_MODELS else model_name


def _build_model_tiers() -> Dict[str, Dict[str, str]]:
    """Built fresh on every call — deliberately NOT a module-level constant.
    A frozen dict computed once at import time would mean a Settings-page
    save (which updates os.environ at runtime) never actually took effect
    until the whole process restarted, silently defeating the point of
    making these fields editable. Every call site below re-reads this."""
    return {
        "primary": {
            "model": _demo_safe(os.getenv("MODEL_NAME", "gpt-4o-mini")),
            "provider": "openai",
            "pricing_key": "gpt-4o-mini",
        },
        "secondary": {
            "model": os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
            "provider": "ollama",
            "pricing_key": "ollama-llama3.1-8b",
        },
        "reasoning": {
            "model": _demo_safe(os.getenv("REASONING_MODEL", "gpt-4o-mini")),
            "provider": "openai",
            "pricing_key": "gpt-4o-mini",
        },
    }


def _ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def _to_langchain_messages(
    messages: List[Dict[str, str]],
) -> List[Union[SystemMessage, HumanMessage, AIMessage]]:
    """Convert plain dicts ``{'role': ..., 'content': ...}`` to LangChain messages."""
    mapping = {
        "system": SystemMessage,
        "human": HumanMessage,
        "user": HumanMessage,
        "assistant": AIMessage,
        "ai": AIMessage,
    }
    result: List[Union[SystemMessage, HumanMessage, AIMessage]] = []
    for msg in messages:
        cls = mapping.get(msg.get("role", "human"), HumanMessage)
        result.append(cls(content=msg["content"]))
    return result


class LLMRouter:
    """Routes LLM calls across three model tiers with automatic token tracking.

    Usage::

        router = LLMRouter()
        result = router.invoke(
            [{"role": "system", "content": "You are a security analyst."},
             {"role": "human", "content": "Summarise these CVEs."}],
            model_tier="primary",
        )
        print(result["content"])
    """

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(
        self,
        session_id: Optional[str] = None,
        use_case: str = "general",
        stage: str = "analysis",
    ) -> None:
        """Initialise the router.

        Args:
            session_id: Current Streamlit session identifier.
            use_case: Active use-case label (``ctem``, ``hunt``, etc.).
            stage: Active lifecycle stage label.
        """
        self._openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        if not self._openai_api_key:
            logger.warning(
                "OPENAI_API_KEY not set — OpenAI tiers will be unavailable."
            )

        self.session_id: str = session_id or "default"
        self.use_case: str = use_case
        self.stage: str = stage

        self._tracker = TokenUsageTracker()

        # Lazy-initialised model instances (one per tier)
        self._models: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Model factory
    # ------------------------------------------------------------------

    def _get_model(
        self,
        tier: str,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> Any:
        """Return (or create) a LangChain chat model for the requested tier."""
        tiers = _build_model_tiers()
        tier_config = tiers.get(tier)
        if tier_config is None:
            raise ValueError(
                f"Unknown model tier '{tier}'. "
                f"Choose from: {list(tiers.keys())}"
            )

        provider = tier_config["provider"]

        if provider == "openai":
            return ChatOpenAI(
                model=tier_config["model"],
                api_key=self._openai_api_key,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
            )

        if provider == "ollama":
            # Import lazily so the app doesn't crash if the package is missing.
            try:
                from langchain_community.chat_models import ChatOllama
            except ImportError:
                raise RuntimeError(
                    "langchain-community is not installed. "
                    "Install it to use the Ollama tier."
                )

            return ChatOllama(
                model=tier_config["model"],
                base_url=_ollama_base_url(),
                temperature=temperature,
                num_predict=max_tokens,
            )

        raise ValueError(f"Unsupported provider: {provider}")

    # ------------------------------------------------------------------
    # Core invocation
    # ------------------------------------------------------------------

    def invoke(
        self,
        messages: List[Dict[str, str]],
        model_tier: str = "primary",
        temperature: float = 0.2,
        max_tokens: int = 2000,
        context: str = "analysis",
    ) -> Dict[str, Any]:
        """Send *messages* to the selected model tier and return a result dict.

        Returns:
            A dict with keys:
            ``content``, ``model``, ``provider``, ``input_tokens``,
            ``output_tokens``, ``duration_ms``.
        """
        tiers = _build_model_tiers()
        tier_config = tiers[model_tier]
        model = self._get_model(model_tier, temperature, max_tokens) if model_tier != "secondary" or self.is_ollama_available() else None  # noqa: E501

        if model is None:
            # Ollama unavailable — fall back to primary OpenAI tier.
            logger.warning(
                "Ollama not available; falling back to primary tier."
            )
            tier_config = tiers["primary"]
            model = self._get_model("primary", temperature, max_tokens)

        lc_messages = _to_langchain_messages(messages)

        start = time.perf_counter()
        try:
            response: AIMessage = model.invoke(lc_messages)  # type: ignore[assignment]
            duration_ms = int((time.perf_counter() - start) * 1000)
            
            # --- Extract token usage from response metadata ---
            usage_meta = getattr(response, "response_metadata", {})
            token_usage = usage_meta.get("token_usage", {})
            input_tokens: int = token_usage.get("prompt_tokens", 0)
            output_tokens: int = token_usage.get("completion_tokens", 0)

            # Fallback: estimate from content length if metadata missing.
            if input_tokens == 0:
                input_tokens = sum(len(m["content"]) // 4 for m in messages)
            if output_tokens == 0:
                output_tokens = len(response.content) // 4 if response.content else 0

            # --- Track usage ---
            self._tracker.track(
                session_id=self.session_id,
                use_case=self.use_case,
                stage=self.stage,
                model=tier_config["model"],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                context=context,
            )

            # Log to health metrics
            try:
                from app.observability.health_metrics import InAppMetrics
                InAppMetrics().record_llm_call(
                    model=tier_config["model"],
                    latency_ms=duration_ms,
                    tokens=input_tokens + output_tokens,
                    success=True
                )
            except Exception as metric_err:
                logger.error("Failed to log LLM metrics: %s", metric_err)

            return {
                "content": response.content,
                "model": tier_config["model"],
                "provider": tier_config["provider"],
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "duration_ms": duration_ms,
            }
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            try:
                from app.observability.health_metrics import InAppMetrics
                InAppMetrics().record_llm_call(
                    model=tier_config["model"],
                    latency_ms=duration_ms,
                    tokens=0,
                    success=False,
                    error=str(exc)
                )
            except Exception as metric_err:
                logger.error("Failed to log LLM failure metrics: %s", metric_err)
            logger.exception("LLM invocation failed on tier=%s", model_tier)
            raise

    # ------------------------------------------------------------------
    # Structured output
    # ------------------------------------------------------------------

    def get_structured_output(
        self,
        messages: List[Dict[str, str]],
        output_schema: Type[BaseModel],
        model_tier: str = "primary",
        temperature: float = 0.1,
        max_tokens: int = 4000,
        context: str = "structured_output",
    ) -> BaseModel:
        """Invoke the LLM and parse its response into a Pydantic model.

        Uses LangChain's ``with_structured_output`` when the provider supports
        it (OpenAI function calling).  Falls back to JSON-mode prompting +
        manual parsing for Ollama.

        Args:
            messages: Conversation messages.
            output_schema: The Pydantic v2 model class to validate against.
            model_tier: Which model tier to route to.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.
            context: Tracking context label.

        Returns:
            A validated instance of *output_schema*.

        Raises:
            ValueError: If the response cannot be parsed into *output_schema*
                after one retry.
        """
        tiers = _build_model_tiers()
        tier_config = tiers.get(model_tier, tiers["primary"])

        # Build the base model
        if tier_config["provider"] == "ollama" and not self.is_ollama_available():
            tier_config = tiers["primary"]
            model_tier = "primary"

        model = self._get_model(model_tier, temperature, max_tokens)

        lc_messages = _to_langchain_messages(messages)

        # Attempt 1 — with_structured_output (OpenAI function calling)
        last_error: Optional[Exception] = None
        for attempt in range(2):
            start = time.perf_counter()
            try:
                if tier_config["provider"] == "openai":
                    structured_model = model.with_structured_output(output_schema)
                    result = structured_model.invoke(lc_messages)
                else:
                    # Ollama: append schema instruction, parse manually
                    schema_json = output_schema.model_json_schema()
                    schema_instruction = (
                        "\n\nYou MUST respond with valid JSON matching this "
                        f"schema:\n```json\n{schema_json}\n```\n"
                        "Return ONLY the JSON object, no other text."
                    )
                    augmented = list(lc_messages)
                    if augmented and isinstance(augmented[-1], HumanMessage):
                        augmented[-1] = HumanMessage(
                            content=augmented[-1].content + schema_instruction
                        )
                    else:
                        augmented.append(HumanMessage(content=schema_instruction))

                    raw_response = model.invoke(augmented)
                    import json

                    raw_text = raw_response.content.strip()
                    # Strip markdown code fences if present
                    if raw_text.startswith("```"):
                        lines = raw_text.split("\n")
                        lines = [
                            l for l in lines if not l.strip().startswith("```")
                        ]
                        raw_text = "\n".join(lines)
                    result = output_schema.model_validate_json(raw_text)

                duration_ms = int((time.perf_counter() - start) * 1000)

                input_tokens = sum(len(m["content"]) // 4 for m in messages)
                output_tokens = 200  # Estimate for structured output

                # Track the call
                self._tracker.track(
                    session_id=self.session_id,
                    use_case=self.use_case,
                    stage=self.stage,
                    model=tier_config["model"],
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                    context=context,
                )

                # Log to health metrics
                try:
                    from app.observability.health_metrics import InAppMetrics
                    InAppMetrics().record_llm_call(
                        model=tier_config["model"],
                        latency_ms=duration_ms,
                        tokens=input_tokens + output_tokens,
                        success=True
                    )
                except Exception as metric_err:
                    logger.error("Failed to log structured LLM metrics: %s", metric_err)

                return result  # type: ignore[return-value]

            except Exception as exc:
                duration_ms = int((time.perf_counter() - start) * 1000)
                try:
                    from app.observability.health_metrics import InAppMetrics
                    InAppMetrics().record_llm_call(
                        model=tier_config["model"],
                        latency_ms=duration_ms,
                        tokens=0,
                        success=False,
                        error=str(exc)
                    )
                except Exception as metric_err:
                    logger.error("Failed to log structured LLM failure metrics: %s", metric_err)
                last_error = exc
                logger.warning(
                    "Structured output attempt %d failed: %s", attempt + 1, exc
                )
                continue

        raise ValueError(
            f"Failed to parse structured output after 2 attempts: {last_error}"
        )

    # ------------------------------------------------------------------
    # Ollama health check
    # ------------------------------------------------------------------

    def is_ollama_available(self) -> bool:
        """Return ``True`` if the Ollama server is reachable."""
        try:
            resp = httpx.get(f"{_ollama_base_url()}/api/tags", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Model info
    # ------------------------------------------------------------------

    def get_active_model_info(self) -> Dict[str, Any]:
        """Return metadata about currently available model tiers."""
        tiers = _build_model_tiers()
        ollama_available = self.is_ollama_available()
        info: Dict[str, Any] = {
            "primary": {
                "model": tiers["primary"]["model"],
                "provider": tiers["primary"]["provider"],
                "status": "available" if self._openai_api_key else "no_api_key",
            },
            "secondary": {
                "model": tiers["secondary"]["model"],
                "provider": tiers["secondary"]["provider"],
                "status": "available" if ollama_available else "unavailable",
            },
            "reasoning": {
                "model": tiers["reasoning"]["model"],
                "provider": tiers["reasoning"]["provider"],
                "status": "available" if self._openai_api_key else "no_api_key",
            },
        }
        return info

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def set_context(
        self,
        use_case: str,
        stage: str,
        session_id: Optional[str] = None,
    ) -> None:
        """Update the tracking context without creating a new router."""
        self.use_case = use_case
        self.stage = stage
        if session_id:
            self.session_id = session_id
