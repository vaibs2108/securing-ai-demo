"""
DataChunkEngine — Map-reduce pipeline for full-dataset LLM analysis.

Splits large DataFrames into manageable chunks (default 500 rows),
processes each chunk through the LLM in parallel, then synthesises
chunk-level results into a single coherent analysis.

This ensures the platform analyses ALL data — never 15-row samples —
while respecting LLM context-window limits.
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Dict, List, Optional

import pandas as pd

from app.llm.router import LLMRouter

logger = logging.getLogger(__name__)


class DataChunkEngine:
    """Map-reduce pipeline for chunked LLM analysis of DataFrames.

    Usage::

        engine = DataChunkEngine(router=LLMRouter(session_id="s1"))
        result = asyncio.run(engine.run_pipeline(
            df=my_dataframe,
            system_prompt="You are a vulnerability analyst.",
            task_prompt="Analyse these vulnerability records and summarise risk.",
        ))
    """

    DEFAULT_CHUNK_SIZE: int = 500
    MAX_CONCURRENT: int = 5  # Limit parallel LLM calls to avoid rate-limits

    def __init__(
        self,
        router: Optional[LLMRouter] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        model_tier: str = "primary",
    ) -> None:
        """Initialise the chunk engine.

        Args:
            router: An ``LLMRouter`` instance. Created with defaults if None.
            chunk_size: Number of DataFrame rows per chunk.
            model_tier: Which model tier to use for chunk analysis.
        """
        self.router: LLMRouter = router or LLMRouter()
        self.chunk_size: int = chunk_size
        self.model_tier: str = model_tier

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def chunk_dataframe(
        self,
        df: pd.DataFrame,
        chunk_size: Optional[int] = None,
    ) -> List[pd.DataFrame]:
        """Split *df* into a list of smaller DataFrames.

        Args:
            df: The source DataFrame.
            chunk_size: Override the default chunk size for this call.

        Returns:
            A list of DataFrame slices (copies, not views).
        """
        size = chunk_size or self.chunk_size
        if size <= 0:
            raise ValueError("chunk_size must be a positive integer")

        num_chunks = math.ceil(len(df) / size)
        chunks: List[pd.DataFrame] = []
        for i in range(num_chunks):
            start = i * size
            end = start + size
            chunks.append(df.iloc[start:end].copy())

        logger.info(
            "Split DataFrame (%d rows) into %d chunks of ~%d rows.",
            len(df),
            len(chunks),
            size,
        )
        return chunks

    # ------------------------------------------------------------------
    # Chunk → text conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _dataframe_to_text(df: pd.DataFrame, chunk_index: int) -> str:
        """Serialise a DataFrame chunk to a compact text representation.

        Uses CSV format for density and readability by the LLM.
        Prepends a header indicating chunk position.
        """
        header = f"--- Chunk {chunk_index + 1} ({len(df)} rows) ---\n"
        # Limit column widths to keep token count manageable
        csv_text = df.to_csv(index=False, lineterminator="\n")
        # Truncate if CSV exceeds ~30 000 chars (~7 500 tokens)
        max_chars = 30_000
        if len(csv_text) > max_chars:
            csv_text = csv_text[:max_chars] + "\n... [truncated]\n"
        return header + csv_text

    # ------------------------------------------------------------------
    # Async chunk analysis
    # ------------------------------------------------------------------

    async def _analyze_single_chunk(
        self,
        chunk_text: str,
        system_prompt: str,
        task_prompt: str,
        semaphore: asyncio.Semaphore,
    ) -> str:
        """Analyse a single text chunk through the LLM.

        Runs the synchronous ``LLMRouter.invoke`` in a thread-pool executor
        to avoid blocking the event loop.
        """
        async with semaphore:
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "human",
                    "content": (
                        f"{task_prompt}\n\n"
                        f"DATA:\n{chunk_text}"
                    ),
                },
            ]

            loop = asyncio.get_running_loop()
            result: Dict[str, Any] = await loop.run_in_executor(
                None,
                lambda: self.router.invoke(
                    messages,
                    model_tier=self.model_tier,
                    temperature=0.2,
                    max_tokens=3000,
                    context="chunk_analysis",
                ),
            )
            return result["content"]

    async def analyze_chunks(
        self,
        chunks: List[pd.DataFrame],
        system_prompt: str,
        task_prompt: str,
    ) -> List[str]:
        """Analyse all DataFrame chunks in parallel (bounded concurrency).

        Args:
            chunks: List of DataFrame slices from :meth:`chunk_dataframe`.
            system_prompt: System-level instructions for the LLM.
            task_prompt: The analysis task description.

        Returns:
            A list of LLM response strings, one per chunk.
        """
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)
        chunk_texts = [
            self._dataframe_to_text(chunk, idx)
            for idx, chunk in enumerate(chunks)
        ]

        tasks = [
            self._analyze_single_chunk(text, system_prompt, task_prompt, semaphore)
            for text in chunk_texts
        ]

        logger.info("Launching parallel analysis of %d chunks.", len(tasks))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error placeholders so partial results survive
        processed: List[str] = []
        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error("Chunk %d failed: %s", idx, res)
                processed.append(f"[Chunk {idx + 1} analysis failed: {res}]")
            else:
                processed.append(res)  # type: ignore[arg-type]

        return processed

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def synthesize(
        self,
        chunk_results: List[str],
        system_prompt: str,
        synthesis_prompt: Optional[str] = None,
    ) -> str:
        """Synthesise multiple chunk analysis results into a single report.

        Args:
            chunk_results: List of per-chunk analysis strings.
            system_prompt: System-level instructions.
            synthesis_prompt: Custom synthesis instructions.  A sensible
                default is used if ``None``.

        Returns:
            The synthesised analysis string.
        """
        default_synthesis = (
            "You are provided with analysis results from multiple data chunks. "
            "Synthesise them into a single, coherent, comprehensive report. "
            "Remove redundancies. Reconcile any conflicting findings. "
            "Produce a final analysis that reads as if it was produced from "
            "the full dataset in one pass.\n\n"
            "Do NOT mention 'chunks' or 'partial results' — present the "
            "output as a unified analysis."
        )

        combined_input = "\n\n".join(
            f"=== Analysis Part {i + 1}/{len(chunk_results)} ===\n{r}"
            for i, r in enumerate(chunk_results)
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "human",
                "content": (
                    f"{synthesis_prompt or default_synthesis}\n\n"
                    f"PARTIAL RESULTS:\n{combined_input}"
                ),
            },
        ]

        result = self.router.invoke(
            messages,
            model_tier=self.model_tier,
            temperature=0.15,
            max_tokens=4000,
            context="chunk_synthesis",
        )
        return result["content"]

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    async def run_pipeline(
        self,
        df: pd.DataFrame,
        system_prompt: str,
        task_prompt: str,
        synthesis_prompt: Optional[str] = None,
        chunk_size: Optional[int] = None,
    ) -> str:
        """End-to-end map-reduce pipeline.

        1. Chunk the DataFrame.
        2. Analyse each chunk in parallel.
        3. Synthesise all chunk results.

        Args:
            df: Source DataFrame.
            system_prompt: System instructions for LLM.
            task_prompt: Analysis task description.
            synthesis_prompt: Optional override for the synthesis step.
            chunk_size: Override default chunk size.

        Returns:
            The final synthesised analysis string.
        """
        if df.empty:
            logger.warning("Empty DataFrame passed to run_pipeline.")
            return "No data available for analysis."

        # 1. Chunk
        chunks = self.chunk_dataframe(df, chunk_size)

        # 2. Map — parallel analysis
        chunk_results = await self.analyze_chunks(
            chunks, system_prompt, task_prompt
        )

        # 3. Reduce — synthesis
        # If only one chunk, skip synthesis overhead
        if len(chunk_results) == 1:
            logger.info("Single chunk — skipping synthesis step.")
            return chunk_results[0]

        logger.info(
            "Synthesising %d chunk results into final report.",
            len(chunk_results),
        )
        final = self.synthesize(chunk_results, system_prompt, synthesis_prompt)
        return final
