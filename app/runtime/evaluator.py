"""
EvaluationEngine — AI analysis quality measurement.

Computes:
- Precision, Recall, F1 scores for finding-level accuracy
- Hallucination rate: percentage of AI-cited facts not present in source data
- Full evaluation reports comparing predicted findings to ground truth

These metrics feed the AI Readiness Index and per-use-case confidence
displays in the executive dashboard.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class EvaluationEngine:
    """Evaluate AI analysis quality against ground truth.

    Usage::

        engine = EvaluationEngine()

        # Basic metrics
        p = engine.compute_precision(tp=42, fp=8)
        r = engine.compute_recall(tp=42, fn=3)
        f1 = engine.compute_f1(p, r)

        # Full evaluation
        report = engine.evaluate_findings(
            predicted=[{"id": "CVE-2024-1234", ...}, ...],
            ground_truth=[{"id": "CVE-2024-1234", ...}, ...],
        )
    """

    # ------------------------------------------------------------------
    # Core metrics
    # ------------------------------------------------------------------

    @staticmethod
    def compute_precision(tp: int, fp: int) -> float:
        """Compute precision = TP / (TP + FP).

        Args:
            tp: True positive count.
            fp: False positive count.

        Returns:
            Precision as a float in [0.0, 1.0].  Returns 0.0 if TP + FP = 0.
        """
        total = tp + fp
        if total == 0:
            return 0.0
        return round(tp / total, 4)

    @staticmethod
    def compute_recall(tp: int, fn: int) -> float:
        """Compute recall = TP / (TP + FN).

        Args:
            tp: True positive count.
            fn: False negative count.

        Returns:
            Recall as a float in [0.0, 1.0].  Returns 0.0 if TP + FN = 0.
        """
        total = tp + fn
        if total == 0:
            return 0.0
        return round(tp / total, 4)

    @staticmethod
    def compute_f1(precision: float, recall: float) -> float:
        """Compute F1 = 2 * (precision * recall) / (precision + recall).

        Args:
            precision: Precision score [0, 1].
            recall: Recall score [0, 1].

        Returns:
            F1 score in [0.0, 1.0].  Returns 0.0 if both inputs are 0.
        """
        total = precision + recall
        if total == 0.0:
            return 0.0
        return round(2.0 * (precision * recall) / total, 4)

    # ------------------------------------------------------------------
    # Hallucination rate
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_facts(text: str) -> Set[str]:
        """Extract atomic factual claims from text for comparison.

        Extracts:
        - CVE IDs (CVE-YYYY-NNNNN)
        - IP addresses
        - Hostnames / FQDNs
        - Numeric values with units
        - CVSS scores (e.g. "CVSS 9.8")
        - Port numbers (e.g. "port 443")

        Returns a normalised set of lowercase fact strings.
        """
        facts: Set[str] = set()

        # CVE IDs
        cves = re.findall(r"CVE-\d{4}-\d{4,}", text, re.IGNORECASE)
        facts.update(c.upper() for c in cves)

        # IP addresses
        ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
        facts.update(ips)

        # Hostnames / FQDNs
        fqdns = re.findall(
            r"\b[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
            r"(?:\.[a-zA-Z]{2,})+\b",
            text,
        )
        facts.update(f.lower() for f in fqdns)

        # CVSS scores
        cvss = re.findall(r"CVSS\s*[:\s]?\s*(\d+\.?\d*)", text, re.IGNORECASE)
        facts.update(f"cvss:{s}" for s in cvss)

        # Port numbers
        ports = re.findall(r"port\s+(\d{1,5})", text, re.IGNORECASE)
        facts.update(f"port:{p}" for p in ports)

        # MITRE ATT&CK technique IDs
        techniques = re.findall(r"T\d{4}(?:\.\d{3})?", text)
        facts.update(t.upper() for t in techniques)

        return facts

    def compute_hallucination_rate(
        self,
        analysis_text: str,
        source_data: str,
    ) -> float:
        """Compute the hallucination rate of an AI analysis.

        Hallucination rate = (# facts in analysis NOT in source) / (# facts in analysis).

        Args:
            analysis_text: The AI-generated analysis text.
            source_data: The source data text (raw data the AI was given).

        Returns:
            Hallucination rate as a float in [0.0, 1.0].
            Returns 0.0 if no extractable facts found in analysis.
        """
        analysis_facts = self._extract_facts(analysis_text)
        source_facts = self._extract_facts(source_data)

        if not analysis_facts:
            return 0.0

        hallucinated = analysis_facts - source_facts
        rate = len(hallucinated) / len(analysis_facts)

        if hallucinated:
            logger.info(
                "Hallucination check: %d/%d facts not in source (%s).",
                len(hallucinated),
                len(analysis_facts),
                ", ".join(sorted(list(hallucinated)[:5])),
            )

        return round(rate, 4)

    # ------------------------------------------------------------------
    # Finding-level evaluation
    # ------------------------------------------------------------------

    def evaluate_findings(
        self,
        predicted: List[Dict[str, Any]],
        ground_truth: List[Dict[str, Any]],
        id_field: str = "id",
    ) -> Dict[str, Any]:
        """Full evaluation comparing predicted findings to ground truth.

        Matching is based on the ``id_field`` (default ``"id"``).

        Args:
            predicted: List of AI-predicted finding dicts.
            ground_truth: List of ground-truth finding dicts.
            id_field: Key name used to match findings.

        Returns:
            Dict with keys:
            - ``precision``, ``recall``, ``f1``: float scores
            - ``true_positives``: int
            - ``false_positives``: int
            - ``false_negatives``: int
            - ``predicted_count``: int
            - ``ground_truth_count``: int
            - ``matched_ids``: list of matched IDs
            - ``missed_ids``: list of IDs in ground truth but not predicted
            - ``extra_ids``: list of IDs in predicted but not in ground truth
        """
        pred_ids: Set[str] = {
            str(f.get(id_field, "")) for f in predicted if f.get(id_field)
        }
        truth_ids: Set[str] = {
            str(f.get(id_field, "")) for f in ground_truth if f.get(id_field)
        }

        tp_ids = pred_ids & truth_ids
        fp_ids = pred_ids - truth_ids
        fn_ids = truth_ids - pred_ids

        tp = len(tp_ids)
        fp = len(fp_ids)
        fn = len(fn_ids)

        precision = self.compute_precision(tp, fp)
        recall = self.compute_recall(tp, fn)
        f1 = self.compute_f1(precision, recall)

        report = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "predicted_count": len(predicted),
            "ground_truth_count": len(ground_truth),
            "matched_ids": sorted(tp_ids),
            "missed_ids": sorted(fn_ids),
            "extra_ids": sorted(fp_ids),
        }

        logger.info(
            "Evaluation: P=%.2f R=%.2f F1=%.2f (TP=%d FP=%d FN=%d)",
            precision,
            recall,
            f1,
            tp,
            fp,
            fn,
        )
        return report

    # ------------------------------------------------------------------
    # Severity-weighted evaluation
    # ------------------------------------------------------------------

    def evaluate_findings_weighted(
        self,
        predicted: List[Dict[str, Any]],
        ground_truth: List[Dict[str, Any]],
        id_field: str = "id",
        severity_field: str = "severity",
    ) -> Dict[str, Any]:
        """Weighted evaluation giving more importance to higher-severity findings.

        Severity weights: critical=4, high=3, medium=2, low=1, info=0.5.
        """
        severity_weights: Dict[str, float] = {
            "critical": 4.0,
            "high": 3.0,
            "medium": 2.0,
            "low": 1.0,
            "info": 0.5,
            "informational": 0.5,
        }

        # Build lookup maps
        pred_map: Dict[str, Dict[str, Any]] = {
            str(f.get(id_field, "")): f for f in predicted if f.get(id_field)
        }
        truth_map: Dict[str, Dict[str, Any]] = {
            str(f.get(id_field, "")): f
            for f in ground_truth
            if f.get(id_field)
        }

        tp_ids = set(pred_map.keys()) & set(truth_map.keys())
        fp_ids = set(pred_map.keys()) - set(truth_map.keys())
        fn_ids = set(truth_map.keys()) - set(pred_map.keys())

        def _weight(finding: Dict[str, Any]) -> float:
            sev = str(finding.get(severity_field, "medium")).lower()
            return severity_weights.get(sev, 1.0)

        weighted_tp = sum(
            _weight(truth_map[fid]) for fid in tp_ids
        )
        weighted_fp = sum(
            _weight(pred_map[fid]) for fid in fp_ids
        )
        weighted_fn = sum(
            _weight(truth_map[fid]) for fid in fn_ids
        )

        w_precision = (
            weighted_tp / (weighted_tp + weighted_fp)
            if (weighted_tp + weighted_fp) > 0
            else 0.0
        )
        w_recall = (
            weighted_tp / (weighted_tp + weighted_fn)
            if (weighted_tp + weighted_fn) > 0
            else 0.0
        )
        w_f1 = (
            2.0 * w_precision * w_recall / (w_precision + w_recall)
            if (w_precision + w_recall) > 0
            else 0.0
        )

        base = self.evaluate_findings(predicted, ground_truth, id_field)
        base.update({
            "weighted_precision": round(w_precision, 4),
            "weighted_recall": round(w_recall, 4),
            "weighted_f1": round(w_f1, 4),
        })
        return base

    # ------------------------------------------------------------------
    # Confidence calibration
    # ------------------------------------------------------------------

    @staticmethod
    def assess_confidence_quality(
        reported_confidence: int,
        actual_precision: float,
    ) -> Dict[str, Any]:
        """Assess whether the AI's confidence score is well-calibrated.

        Args:
            reported_confidence: AI's self-reported confidence (0-100).
            actual_precision: Measured precision from evaluation.

        Returns:
            Dict with ``calibration_error``, ``assessment`` label,
            and ``recommendation``.
        """
        expected = reported_confidence / 100.0
        error = abs(expected - actual_precision)

        if error <= 0.05:
            assessment = "well_calibrated"
            recommendation = "Confidence scores are reliable."
        elif error <= 0.15:
            assessment = "slightly_miscalibrated"
            recommendation = (
                "Confidence scores are approximately reliable. "
                "Minor adjustments may improve accuracy."
            )
        elif expected > actual_precision:
            assessment = "overconfident"
            recommendation = (
                "AI is over-estimating its accuracy. Consider lowering "
                "HITL confidence thresholds to catch more errors."
            )
        else:
            assessment = "underconfident"
            recommendation = (
                "AI is under-estimating its accuracy. HITL gates may "
                "be triggering unnecessarily."
            )

        return {
            "reported_confidence": reported_confidence,
            "actual_precision": round(actual_precision, 4),
            "calibration_error": round(error, 4),
            "assessment": assessment,
            "recommendation": recommendation,
        }
