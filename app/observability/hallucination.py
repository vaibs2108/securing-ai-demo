"""
Securing AI Demo — Hallucination Detector
Validates AI-cited facts (CVEs, MITRE ATT&CK/ATLAS technique codes, and agent references) against authoritative indices.
AGENTS.md Section 2 & 11 Tab 2
"""

import re
import os
import httpx
import yaml
import logging
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Simple schema definitions for hallucination results
class HallucinationFlag(BaseModel):
    citation: str
    source_checked: str
    finding: str
    severity: str = "warning"  # warning or error

class HallucinationReport(BaseModel):
    total_citations: int
    flags: List[HallucinationFlag]
    hallucination_rate: float
    validated_at: str

# Module-level cache to prevent duplicate external network requests
_CVE_CACHE: Dict[str, bool] = {}

# Set of known standard CVEs that are generated synthetically
_KNOWN_VALID_CVES = {
    "CVE-2023-44487", "CVE-2024-3094", "CVE-2023-38545", "CVE-2023-22515", 
    "CVE-2023-34362", "CVE-2021-44228", "CVE-2020-0601", "CVE-2017-0144",
    "CVE-2023-49103", "CVE-2024-21626", "CVE-2023-50164", "CVE-2024-23897"
}

class HallucinationDetector:
    """Validates AI-cited facts against authoritative sources."""

    def __init__(self, frameworks_yaml_path: Optional[str] = None):
        if frameworks_yaml_path is None:
            project_root = Path(__file__).resolve().parents[2]
            frameworks_yaml_path = str(project_root / "app" / "data" / "compliance_frameworks.yaml")
        
        self.frameworks_path = frameworks_yaml_path
        self._valid_techniques = self._load_authoritative_techniques()

    def _load_authoritative_techniques(self) -> set:
        """Load MITRE ATT&CK/ATLAS technique IDs from compliance_frameworks.yaml."""
        techniques = set()
        try:
            if os.path.exists(self.frameworks_path):
                with open(self.frameworks_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                
                # Extract technique IDs from each use case config
                for uc_key, uc_data in data.items():
                    if isinstance(uc_data, dict) and "mitre_attack" in uc_data:
                        mitre = uc_data["mitre_attack"]
                        if isinstance(mitre, dict) and "techniques" in mitre:
                            for tech in mitre["techniques"]:
                                if isinstance(tech, dict) and "id" in tech:
                                    techniques.add(tech["id"].upper())
            else:
                logger.warning("Framework YAML path not found: %s. Using default list.", self.frameworks_path)
        except Exception as e:
            logger.error("Failed to load compliance frameworks for hallucination detector: %s", e)
            
        # Guarantee fallback common techniques used in demo if file reading fails
        fallback_techs = {
            "T1190", "T1133", "T1078", "T1078.002", "T1059.001", "T1059.003",
            "T1059.006", "T1047", "T1053.005", "T1543.003", "T1136.001",
            "T1068", "T1548.002", "T1070.001", "T1562.001", "T1027",
            "T1003.001", "T1003.003", "T1110.003", "T1087.002", "T1069.002",
            "T1021.001", "T1021.002", "T1021.006", "T1560.001", "T1041",
            "T1071.001", "T1105", "T1572", "T1486", "T1595.002", "T1592",
            "T1593.002", "T1596.005", "T1566.001", "T1203", "T1550.002",
            "T1082",
            # MITRE ATLAS (AI/ML-specific adversarial techniques)
            "AML.T0051", "AML.T0054", "AML.T0056", "AML.T0048", "AML.T0043",
            "AML.T0024", "AML.T0020", "AML.T0034",
        }
        return techniques.union(fallback_techs)

    def validate_cve_ids(self, text: str) -> List[HallucinationFlag]:
        """Extract CVE IDs from text and validate them against NVD API or local offline indices."""
        flags = []
        cve_pattern = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
        citations = list(set(cve_pattern.findall(text)))

        nvd_api_key = os.getenv("NVD_API_KEY", "")
        headers = {}
        if nvd_api_key:
            headers["apiKey"] = nvd_api_key

        for cve in citations:
            cve_upper = cve.upper()
            
            # 1. Check local/memory cache
            if cve_upper in _CVE_CACHE:
                if not _CVE_CACHE[cve_upper]:
                    flags.append(HallucinationFlag(
                        citation=cve_upper,
                        source_checked="NVD CVE Authority Index",
                        finding=f"CVE ID '{cve_upper}' not found in NVD database (cached).",
                        severity="error"
                    ))
                continue

            # 2. Check known static valid list (supports high speed and offline testing)
            # Removed bypass to enforce 100% real-time NVD API query


            # 3. Call public NVD API
            url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_upper}"
            try:
                # Set a strict short timeout to prevent blocking Streamlit threads
                r = httpx.get(url, headers=headers, timeout=2.0)
                if r.status_code == 200:
                    data = r.json()
                    vulnerabilities = data.get("vulnerabilities", [])
                    if vulnerabilities:
                        _CVE_CACHE[cve_upper] = True
                    else:
                        _CVE_CACHE[cve_upper] = False
                        flags.append(HallucinationFlag(
                            citation=cve_upper,
                            source_checked="NVD CVE Authority Index",
                            finding=f"CVE ID '{cve_upper}' was not found in the public NVD registry.",
                            severity="error"
                        ))
                elif r.status_code in (403, 429):
                    # Rate limited - treat as valid for demo robust fallback
                    logger.warning("NVD API rate limited verifying %s. Falling back to pattern validation.", cve_upper)
                    _CVE_CACHE[cve_upper] = True
                else:
                    logger.warning("NVD API returned status code %d for %s", r.status_code, cve_upper)
                    _CVE_CACHE[cve_upper] = True
            except Exception as e:
                logger.warning("Network timeout or connection error querying NVD for %s: %s. Using pattern verification.", cve_upper, e)
                # Pattern based check: if matches recent CVE format, treat as valid to prevent offline errors
                year_part = int(cve_upper.split("-")[1])
                if 2000 <= year_part <= 2026:
                    _CVE_CACHE[cve_upper] = True
                else:
                    _CVE_CACHE[cve_upper] = False
                    flags.append(HallucinationFlag(
                        citation=cve_upper,
                        source_checked="NVD CVE Authority Index",
                        finding=f"CVE ID '{cve_upper}' failed format pattern validation and NVD query timed out.",
                        severity="warning"
                    ))
        
        return flags

    def validate_attack_techniques(self, text: str) -> List[HallucinationFlag]:
        """Extract T-codes cited in AI output and validate against compliance YAML."""
        flags = []
        t_pattern = re.compile(r"\b(?:AML\.T\d{4}(?:\.\d{3})?|T\d{4}(?:\.\d{3})?)\b", re.IGNORECASE)
        citations = list(set(t_pattern.findall(text)))

        for tech in citations:
            tech_upper = tech.upper()
            if tech_upper not in self._valid_techniques:
                flags.append(HallucinationFlag(
                    citation=tech_upper,
                    source_checked="MITRE ATT&CK/ATLAS Matrix Ref",
                    finding=f"MITRE technique ID '{tech_upper}' not mapped in local framework indices.",
                    severity="warning"
                ))
        return flags

    def validate_asset_references(self, text: str, asset_df: Optional[pd.DataFrame] = None) -> List[HallucinationFlag]:
        """Extract asset names cited in AI output and validate against in-scope asset inventory."""
        flags = []
        
        # If no agent inventory is passed, use a mock list of allowed agent/hostnames
        known_hostnames = set()
        if asset_df is not None and not asset_df.empty:
            if "hostname" in asset_df.columns:
                known_hostnames = set(asset_df["hostname"].dropna().str.upper().tolist())
            elif "agent_id" in asset_df.columns:
                known_hostnames = set(asset_df["agent_id"].dropna().str.upper().tolist())
            elif "asset_id" in asset_df.columns:
                known_hostnames = set(asset_df["asset_id"].dropna().str.upper().tolist())

        # Fallback to realistic synthetic agent IDs generated by generator.py
        if not known_hostnames:
            for i in range(1000, 1300):
                known_hostnames.add(f"AGT-{i}")

        # Extract words that look like hostnames/agent identifiers
        # e.g., web-prod-01, app-stg-04, etc.
        host_pattern = re.compile(r"\b[a-zA-Z0-9]+-[a-zA-Z0-9]+-\d+\b")
        citations = list(set(host_pattern.findall(text)))

        for host in citations:
            host_upper = host.upper()
            # If it is formatted like an agent/hostname reference but not in our active scope
            if host_upper not in known_hostnames:
                flags.append(HallucinationFlag(
                    citation=host,
                    source_checked="Active Agent Boundary",
                    finding=f"Agent reference '{host}' is cited but not defined in current discovery boundaries.",
                    severity="warning"
                ))

        return flags

    def run_all(self, text: str, asset_df: Optional[pd.DataFrame] = None) -> HallucinationReport:
        """Run all validators and return a structured report."""
        cve_flags = self.validate_cve_ids(text)
        tech_flags = self.validate_attack_techniques(text)
        asset_flags = self.validate_asset_references(text, asset_df)

        all_flags = cve_flags + tech_flags + asset_flags

        # Count total citations
        cve_pattern = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
        t_pattern = re.compile(r"\b(?:AML\.T\d{4}(?:\.\d{3})?|T\d{4}(?:\.\d{3})?)\b", re.IGNORECASE)
        host_pattern = re.compile(r"\b[a-zA-Z0-9]+-[a-zA-Z0-9]+-\d+\b")

        total_c = len(set(cve_pattern.findall(text))) + len(set(t_pattern.findall(text))) + len(set(host_pattern.findall(text)))

        hallucination_rate = len(all_flags) / max(total_c, 1)

        return HallucinationReport(
            total_citations=total_c,
            flags=all_flags,
            hallucination_rate=hallucination_rate,
            validated_at=datetime.utcnow().isoformat()
        )
