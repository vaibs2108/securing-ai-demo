"""
AI Capability Demo — Base Transformer
Defines the abstract interface and base utility methods for normalising vendor security payloads
to the platform's unified schema.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

class BaseTransformer(ABC):
    """Abstract base class for all security tool data normalisers."""

    @abstractmethod
    def transform_asset(self, raw_asset: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise a single raw asset payload from the vendor tool."""
        pass

    @abstractmethod
    def transform_vulnerability(self, raw_vuln: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise a single raw vulnerability finding from the vendor tool."""
        pass

    def transform_assets(self, raw_assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Batch transform raw assets."""
        return [self.transform_asset(asset) for asset in raw_assets if asset]

    def transform_vulnerabilities(self, raw_vulns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Batch transform raw vulnerability findings."""
        return [self.transform_vulnerability(vuln) for vuln in raw_vulns if vuln]

    # ── Common Helpers ────────────────────────────────────────────────────────

    def clean_string(self, val: Any) -> str:
        """Helper to ensure values are safe, trimmed strings."""
        if val is None:
            return ""
        return str(val).strip()

    def parse_cvss(self, val: Any) -> float:
        """Helper to parse and validate CVSS scores."""
        try:
            score = float(val)
            if 0.0 <= score <= 10.0:
                return score
            return 0.0
        except (ValueError, TypeError):
            return 0.0

    def parse_epss(self, val: Any) -> float:
        """Helper to parse and validate EPSS scores."""
        try:
            score = float(val)
            if 0.0 <= score <= 1.0:
                return score
            return 0.0
        except (ValueError, TypeError):
            return 0.0

    def map_severity(self, cvss: float) -> str:
        """Standardised CVSS to severity label mapping."""
        if cvss >= 9.0:
            return "Critical"
        elif cvss >= 7.0:
            return "High"
        elif cvss >= 4.0:
            return "Medium"
        return "Low"
